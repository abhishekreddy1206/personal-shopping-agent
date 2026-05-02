from __future__ import annotations

import urllib.parse

from app.models.types import EvidenceSnapshot, OfferCandidate, ParsedIntent
from app.sources.live_fetch import LiveFetchClient
from app.sources.search_utils import choose_best_lines


class GenericRetailLiveAdapter:
    def __init__(
        self,
        *,
        name: str,
        retailer: str,
        category: str,
        search_url_template: str,
        client: LiveFetchClient,
        source_role: str = "truth",
        lane: str = "trusted_retail",
        verification_state: str = "unverified",
        extraction_confidence: str = "low",
        condition: str = "new",
        require_price: bool = False,
    ) -> None:
        self.name = name
        self.retailer = retailer
        self.category = category
        self.search_url_template = search_url_template
        self.client = client
        self.source_role = source_role
        self.lane = lane
        self.verification_state = verification_state
        self.extraction_confidence = extraction_confidence
        self.condition = condition
        self.require_price = require_price

    def search(self, intent: ParsedIntent) -> list[OfferCandidate]:
        search_text = intent.filters.get("product_text") or intent.raw_query
        query = urllib.parse.quote_plus(search_text)
        url = self.search_url_template.format(query=query)
        text = self.client.fetch_text(url)
        if not text:
            return []
        snapshot = self.client.save_snapshot(self.name, search_text, text)
        candidates = choose_best_lines(text, intent)
        offers: list[OfferCandidate] = []
        for title, price, score, analysis in candidates:
            if score < 0.34 and price is None:
                continue
            if self.require_price and price is None:
                continue
            normalized_title = self._normalize_title(title, intent, analysis)
            offers.append(
                OfferCandidate(
                    source_name=self.name,
                    retailer=self.retailer,
                    listing_url=url,
                    title=normalized_title,
                    base_price=price,
                    shipping_price=0.0,
                    effective_price=price,
                    condition=self.condition,
                    availability="unknown",
                    metadata={
                        "snapshot_path": snapshot,
                        "confidence": "medium" if score >= 0.72 else "low",
                        "match_score": round(score, 3),
                        "exact_model_match": bool(analysis.get("exact_model_match")),
                        "generic_result": bool(analysis.get("is_generic")),
                        "price_known": price is not None,
                        "source_mode": "live_extract",
                        "lane": self.lane,
                        "trust_tier": "high" if self.source_role == "truth" else "medium",
                    },
                    evidence_snapshot=EvidenceSnapshot(
                        source_name=self.name,
                        storage_path=snapshot,
                        capture_method="live_fetch",
                        sanitized=True,
                        retention_policy="local_debug",
                    ),
                    source_role=self.source_role,
                    verification_state=self.verification_state,
                    extraction_confidence="medium" if score >= 0.72 else self.extraction_confidence,
                )
            )
        return offers

    def _normalize_title(self, title: str, intent: ParsedIntent, analysis: dict[str, object]) -> str:
        compact = " ".join(title.split())
        if len(compact.split()) >= 3:
            return compact
        if not analysis.get("exact_model_match"):
            return compact
        brand = (intent.filters.get("brand") if intent.filters else None) or ""
        family = (intent.filters.get("product_family") if intent.filters else None) or ""
        model = (intent.filters.get("model_number") if intent.filters else None) or ""
        pieces = [brand, model, family.title() if family else ""]
        expanded = " ".join(piece for piece in pieces if piece).strip()
        return expanded or compact
