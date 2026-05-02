from __future__ import annotations

from app.models.types import EvidenceSnapshot, OfferCandidate, ParsedIntent


class BestBuyAdapter:
    name = "best_buy"
    category = "electronics"

    def search(self, intent: ParsedIntent) -> list[OfferCandidate]:
        title = (intent.filters.get("product_text") if intent.filters else None) or " ".join(intent.product_terms) or intent.raw_query
        return [
            OfferCandidate(
                source_name=self.name,
                retailer="Best Buy",
                listing_url="https://www.bestbuy.com/site/searchpage.jsp?st=" + title.replace(" ", "+"),
                title=title + " — Best Buy candidate",
                base_price=299.99,
                shipping_price=0.0,
                effective_price=299.99,
                condition="new",
                availability="in_stock",
                metadata={
                    "confidence": "medium",
                    "source_mode": "fallback_stub",
                    "lane": "trusted_retail",
                    "price_is_placeholder": True,
                    "pricing_note": "Demo placeholder price until live extraction succeeds",
                },
                evidence_snapshot=EvidenceSnapshot(
                    source_name=self.name,
                    capture_method="fallback_stub",
                    sanitized=True,
                    retention_policy="derived_only",
                ),
                source_role="truth",
                verification_state="partially_verified",
                extraction_confidence="medium",
            )
        ]
