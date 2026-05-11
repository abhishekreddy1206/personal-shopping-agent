from __future__ import annotations

from app.models.types import EvidenceSnapshot, OfferCandidate, ParsedIntent
from app.sources.live_fetch import LiveFetchClient
from app.sources.search_utils import choose_best_lines, prepare_search_lines


class EbayMarketplaceAdapter:
    def __init__(self, client: LiveFetchClient, category: str = "electronics") -> None:
        self.client = client
        self.category = category
        self.name = "ebay_live"
        self.retailer = "eBay"
        self.search_url_template = "https://www.ebay.com/sch/i.html?_nkw={query}"

    def search(self, intent: ParsedIntent) -> list[OfferCandidate]:
        import urllib.parse

        search_text = intent.filters.get("product_text") or intent.raw_query
        query = urllib.parse.quote_plus(search_text)
        url = self.search_url_template.format(query=query)
        text = self.client.fetch_text(url)
        if not text:
            return []
        snapshot = self.client.save_snapshot(self.name, search_text, text)
        candidates = choose_best_lines(text, intent, max_candidates=6)
        offers: list[OfferCandidate] = []
        for title, price, score, analysis in candidates:
            if price is None:
                continue
            condition = self._infer_condition(title)
            offers.append(
                OfferCandidate(
                    source_name=self.name,
                    retailer=self.retailer,
                    listing_url=url,
                    title=" ".join(title.split()),
                    base_price=price,
                    shipping_price=0.0,
                    effective_price=price,
                    condition=condition,
                    availability="unknown",
                    metadata={
                        "snapshot_path": snapshot,
                        "confidence": "medium" if score >= 0.72 else "low",
                        "match_score": round(score, 3),
                        "exact_model_match": bool(analysis.get("exact_model_match")),
                        "generic_result": bool(analysis.get("is_generic")),
                        "price_known": True,
                        "source_mode": "live_extract",
                        "lane": "marketplace",
                        "trust_tier": "medium",
                    },
                    evidence_snapshot=EvidenceSnapshot(
                        source_name=self.name,
                        storage_path=snapshot,
                        capture_method="live_fetch",
                        sanitized=True,
                        retention_policy="local_debug",
                    ),
                    source_role="marketplace",
                    verification_state="seller_unverified",
                    extraction_confidence="medium" if score >= 0.72 else "low",
                )
            )
        return self._dedupe(offers)

    def _infer_condition(self, title: str) -> str:
        lowered = title.lower()
        if "new" in lowered or "brand new" in lowered:
            return "new"
        if "open box" in lowered or "open-box" in lowered:
            return "open_box"
        if "refurb" in lowered or "renewed" in lowered:
            return "refurbished"
        return "used"

    def _dedupe(self, offers: list[OfferCandidate]) -> list[OfferCandidate]:
        deduped: list[OfferCandidate] = []
        seen = set()
        for offer in offers:
            key = (offer.title.lower(), offer.effective_price, offer.condition)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(offer)
        return deduped
