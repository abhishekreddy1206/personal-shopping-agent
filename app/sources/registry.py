from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path

import yaml

from app.models.types import OfferCandidate, ParsedIntent
from app.sources.discovery_adapter import DiscoverySearchAdapter
from app.sources.ebay_adapter import EbayMarketplaceAdapter
from app.sources.live_fetch import LiveAmazonSearchAdapter, LiveFetchClient, LiveNikeSearchAdapter
from app.sources.retail_live_adapter import GenericRetailLiveAdapter
from app.sources.search_utils import suppress_stub_offers


logger = logging.getLogger(__name__)


RETAIL_SEARCH_URLS = {
    "amazon": "https://www.amazon.com/s?k={query}",
    "best_buy": "https://www.bestbuy.com/site/searchpage.jsp?st={query}",
    "walmart": "https://www.walmart.com/search?q={query}",
    "target": "https://www.target.com/s?searchTerm={query}",
    "newegg": "https://www.newegg.com/p/pl?d={query}",
    "bh_photo": "https://www.bhphotovideo.com/c/search?q={query}",
}

DISCOVERY_SEARCH_URLS = {
    "slickdeals": "https://slickdeals.net/newsearch.php?q={query}",
}

TRUSTED_RETAILERS = {"amazon", "best_buy", "walmart", "target", "newegg", "bh_photo", "nike"}

# Per-adapter wall-clock budget. A single slow retailer will not stall the whole search.
PER_ADAPTER_TIMEOUT_S = 3.5
# Total wall-clock budget for the whole search. Telegram users will see a response in under ~10s.
TOTAL_SEARCH_BUDGET_S = 8.0
# Bound the executor so we don't spin up too many threads if many adapters are enabled.
MAX_WORKERS = 8


class SourceRegistry:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2]
        raw_dir = root / "data" / "raw"
        config_path = root / "config" / "retailers.yaml"
        self.config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.live_client = LiveFetchClient(raw_dir)

        self._trusted_by_category = self._build_trusted_adapters()
        self._discovery_by_category = self._build_discovery_adapters()
        self._marketplace_by_category = self._build_marketplace_adapters()

        # Last-run telemetry, exposed so callers can show users why a lane returned 0.
        self.last_telemetry: list[dict] = []

    def search(self, intent: ParsedIntent) -> list[OfferCandidate]:
        """Run every adapter for the requested mode in parallel and return surviving offers.

        Telemetry from the last run is available at `self.last_telemetry`; the orchestrator
        forwards it into the response payload when debug mode is on.
        """
        source_mode = intent.filters.get("source_mode", "trusted_plus_discovery")
        adapters = list(self._trusted_by_category.get(intent.category or "", []))
        if source_mode in {"trusted_plus_discovery", "aggressive_deal_hunt"}:
            adapters.extend(self._discovery_by_category.get(intent.category or "", []))
        if source_mode in {"trusted_plus_marketplace", "aggressive_deal_hunt"}:
            adapters.extend(self._marketplace_by_category.get(intent.category or "", []))

        offers, telemetry = self._run_adapters_parallel(adapters, intent)
        self.last_telemetry = telemetry

        for offer in offers:
            offer.metadata.setdefault("source_mode_requested", source_mode)
            offer.metadata.setdefault("source_family", self._family_for_offer(offer))
            offer.metadata.setdefault("condition_display", offer.condition or "unknown")
            if offer.source_role == "truth":
                offer.metadata.setdefault("trust_tier", "high")
            elif offer.source_role == "marketplace":
                offer.metadata.setdefault("trust_tier", "medium")
            else:
                offer.metadata.setdefault("trust_tier", "medium")

        # Defensive: nothing in the current adapter set produces fallback stubs, but the
        # filter stays so any future regression that reintroduces them gets dropped at the
        # registry boundary. Policy: only real, web-sourced prices reach the user.
        offers = suppress_stub_offers(offers)
        offers = self._filter_default_clutter(offers, intent)
        return self._apply_enrichment_placeholders(offers)

    def _run_adapters_parallel(
        self,
        adapters: list,
        intent: ParsedIntent,
    ) -> tuple[list[OfferCandidate], list[dict]]:
        offers: list[OfferCandidate] = []
        telemetry: list[dict] = []
        if not adapters:
            return offers, telemetry

        deadline = time.monotonic() + TOTAL_SEARCH_BUDGET_S

        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(adapters))) as executor:
            future_to_adapter = {}
            start_times: dict = {}
            for adapter in adapters:
                start = time.monotonic()
                start_times[id(adapter)] = (adapter, start)
                future = executor.submit(self._run_adapter_safely, adapter, intent)
                future_to_adapter[future] = adapter

            try:
                for future in as_completed(future_to_adapter, timeout=TOTAL_SEARCH_BUDGET_S):
                    adapter = future_to_adapter[future]
                    name = getattr(adapter, "name", adapter.__class__.__name__)
                    _, started = start_times[id(adapter)]
                    duration_ms = round((time.monotonic() - started) * 1000)
                    try:
                        adapter_offers = future.result(timeout=max(0.0, deadline - time.monotonic()))
                    except Exception as exc:
                        logger.warning("adapter %s failed after %dms: %s: %s", name, duration_ms, exc.__class__.__name__, exc)
                        telemetry.append({
                            "adapter": name,
                            "status": "error",
                            "error_class": exc.__class__.__name__,
                            "error_message": str(exc)[:200],
                            "duration_ms": duration_ms,
                            "offer_count": 0,
                        })
                        continue
                    offers.extend(adapter_offers)
                    telemetry.append({
                        "adapter": name,
                        "status": "ok",
                        "duration_ms": duration_ms,
                        "offer_count": len(adapter_offers),
                    })
                    logger.info("adapter %s returned %d offer(s) in %dms", name, len(adapter_offers), duration_ms)
            except (TimeoutError, FuturesTimeoutError):
                # Catch any adapters that didn't finish before the global budget elapsed.
                # Both error types matter: builtin TimeoutError on Python 3.11+ and
                # concurrent.futures.TimeoutError on older interpreters.
                for future, adapter in future_to_adapter.items():
                    if future.done():
                        continue
                    name = getattr(adapter, "name", adapter.__class__.__name__)
                    _, started = start_times[id(adapter)]
                    duration_ms = round((time.monotonic() - started) * 1000)
                    logger.warning("adapter %s exceeded %.1fs total budget at %dms", name, TOTAL_SEARCH_BUDGET_S, duration_ms)
                    telemetry.append({
                        "adapter": name,
                        "status": "timeout",
                        "duration_ms": duration_ms,
                        "offer_count": 0,
                    })
                    future.cancel()

        return offers, telemetry

    def _run_adapter_safely(self, adapter, intent: ParsedIntent) -> list[OfferCandidate]:
        # Each adapter runs on its own thread; this wrapper exists so we can later add
        # per-adapter timeouts without touching call sites. For now, the per-fetch timeout
        # in LiveFetchClient (4s) keeps any single adapter from running longer than ~5s.
        return adapter.search(intent)

    def _build_trusted_adapters(self) -> dict[str, list]:
        trusted: dict[str, list] = {"electronics": [], "clothes_shoes": []}
        for category, retailer_configs in self.config.get("retailers", {}).items():
            for entry in retailer_configs:
                if not entry.get("enabled"):
                    continue
                name = entry["name"]
                if category == "electronics" and name == "amazon":
                    trusted[category].append(LiveAmazonSearchAdapter(self.live_client))
                    continue
                if category == "electronics" and name == "best_buy":
                    trusted[category].append(
                        GenericRetailLiveAdapter(
                            name="best_buy_live",
                            retailer="Best Buy",
                            category=category,
                            search_url_template=RETAIL_SEARCH_URLS[name],
                            client=self.live_client,
                        )
                    )
                    continue
                if category == "clothes_shoes" and name == "nike":
                    trusted[category].append(LiveNikeSearchAdapter(self.live_client))
                    continue
                if name in RETAIL_SEARCH_URLS:
                    trusted[category].append(
                        GenericRetailLiveAdapter(
                            name=f"{name}_live",
                            retailer=self._display_name(name),
                            category=category,
                            search_url_template=RETAIL_SEARCH_URLS[name],
                            client=self.live_client,
                            require_price=name in {"newegg", "target", "bh_photo"},
                        )
                    )
        return trusted

    def _build_discovery_adapters(self) -> dict[str, list]:
        discovery = {"electronics": [], "clothes_shoes": []}
        for entry in self.config.get("discovery_sources", []):
            if not entry.get("enabled"):
                continue
            name = entry["name"]
            if name in DISCOVERY_SEARCH_URLS:
                for category in discovery:
                    discovery[category].append(
                        DiscoverySearchAdapter(
                            name=f"{name}_live",
                            retailer=self._display_name(name),
                            category=category,
                            search_url_template=DISCOVERY_SEARCH_URLS[name],
                            client=self.live_client,
                        )
                    )
        return discovery

    def _build_marketplace_adapters(self) -> dict[str, list]:
        marketplace = {"electronics": [], "clothes_shoes": []}
        for entry in self.config.get("marketplace_sources", []):
            if not entry.get("enabled"):
                continue
            if entry["name"] == "ebay":
                for category in marketplace:
                    marketplace[category].append(EbayMarketplaceAdapter(self.live_client, category=category))
        return marketplace

    def _filter_default_clutter(self, offers: list[OfferCandidate], intent: ParsedIntent) -> list[OfferCandidate]:
        requested_mode = intent.filters.get("source_mode", "trusted_plus_discovery") if intent.filters else "trusted_plus_discovery"
        allow_marketplace = requested_mode in {"trusted_plus_marketplace", "aggressive_deal_hunt"}
        allow_discovery = requested_mode == "aggressive_deal_hunt"
        preferred_condition = (intent.condition_preference or "any").lower()

        filtered: list[OfferCandidate] = []
        for offer in offers:
            lane = offer.metadata.get("lane") or offer.metadata.get("source_family") or "trusted_retail"
            condition = (offer.condition or "unknown").lower()
            if lane == "marketplace" and not allow_marketplace:
                continue
            if lane == "discovery" and not allow_discovery:
                continue
            if preferred_condition not in {"used", "refurbished"} and condition in {"used", "refurbished", "open_box", "unknown"} and lane != "trusted_retail":
                continue
            if preferred_condition == "new" and condition in {"used", "refurbished", "open_box"}:
                continue
            filtered.append(offer)
        return filtered

    def _apply_enrichment_placeholders(self, offers: list[OfferCandidate]) -> list[OfferCandidate]:
        for offer in offers:
            offer.metadata.setdefault(
                "enrichment",
                {
                    "price_history": {"status": "not_connected", "applied": False},
                    "coupon": {"status": "not_connected", "applied": False},
                    "cashback": {"status": "not_connected", "applied": False},
                },
            )
        return offers

    def _display_name(self, name: str) -> str:
        mapping = {
            "best_buy": "Best Buy",
            "bh_photo": "B&H",
            "slickdeals": "Slickdeals",
        }
        return mapping.get(name, name.replace("_", " ").title())

    def _family_for_offer(self, offer: OfferCandidate) -> str:
        if offer.source_role == "marketplace":
            return "marketplace"
        if offer.source_role == "discovery":
            return "discovery"
        if offer.source_name.replace("_live", "") in TRUSTED_RETAILERS:
            return "trusted_retail"
        return offer.metadata.get("lane", "trusted_retail")
