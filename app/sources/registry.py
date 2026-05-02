from __future__ import annotations

from pathlib import Path

import yaml

from app.models.types import OfferCandidate, ParsedIntent
from app.sources.amazon_adapter import AmazonAdapter
from app.sources.bestbuy_adapter import BestBuyAdapter
from app.sources.discovery_adapter import DiscoverySearchAdapter
from app.sources.ebay_adapter import EbayMarketplaceAdapter
from app.sources.live_fetch import LiveAmazonSearchAdapter, LiveFetchClient, LiveNikeSearchAdapter
from app.sources.nike_adapter import NikeAdapter
from app.sources.retail_live_adapter import GenericRetailLiveAdapter
from app.sources.search_utils import suppress_stub_offers


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

    def search(self, intent: ParsedIntent) -> list[OfferCandidate]:
        source_mode = intent.filters.get("source_mode", "trusted_plus_discovery")
        adapters = list(self._trusted_by_category.get(intent.category or "", []))
        if source_mode in {"trusted_plus_discovery", "aggressive_deal_hunt"}:
            adapters.extend(self._discovery_by_category.get(intent.category or "", []))
        if source_mode in {"trusted_plus_marketplace", "aggressive_deal_hunt"}:
            adapters.extend(self._marketplace_by_category.get(intent.category or "", []))

        offers: list[OfferCandidate] = []
        for adapter in adapters:
            try:
                adapter_offers = adapter.search(intent)
                for offer in adapter_offers:
                    offer.metadata.setdefault("source_mode_requested", source_mode)
                    offer.metadata.setdefault("source_family", self._family_for_offer(offer))
                    offer.metadata.setdefault("condition_display", offer.condition or "unknown")
                    if offer.source_role == "truth":
                        offer.metadata.setdefault("trust_tier", "high")
                    elif offer.source_role == "marketplace":
                        offer.metadata.setdefault("trust_tier", "medium")
                    else:
                        offer.metadata.setdefault("trust_tier", "medium")
                offers.extend(adapter_offers)
            except Exception:
                continue

        offers = suppress_stub_offers(offers)
        offers = self._filter_default_clutter(offers, intent)
        return self._apply_enrichment_placeholders(offers)

    def _build_trusted_adapters(self) -> dict[str, list]:
        trusted: dict[str, list] = {"electronics": [], "clothes_shoes": []}
        for category, retailer_configs in self.config.get("retailers", {}).items():
            for entry in retailer_configs:
                if not entry.get("enabled"):
                    continue
                name = entry["name"]
                if category == "electronics" and name == "amazon":
                    trusted[category].append(LiveAmazonSearchAdapter(self.live_client))
                    trusted[category].append(AmazonAdapter())
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
                    trusted[category].append(BestBuyAdapter())
                    continue
                if category == "clothes_shoes" and name == "nike":
                    trusted[category].append(LiveNikeSearchAdapter(self.live_client))
                    trusted[category].append(NikeAdapter())
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
