from __future__ import annotations

from app.models.types import EvidenceSnapshot, OfferCandidate, ParsedIntent


class AmazonAdapter:
    name = "amazon"
    category = "electronics"

    def search(self, intent: ParsedIntent) -> list[OfferCandidate]:
        title = (intent.filters.get("product_text") if intent.filters else None) or " ".join(intent.product_terms) or intent.raw_query
        return [
            OfferCandidate(
                source_name=self.name,
                retailer="Amazon",
                listing_url="https://www.amazon.com/s?k=" + title.replace(" ", "+"),
                title=title + " — Amazon candidate",
                base_price=289.99,
                shipping_price=9.99,
                effective_price=299.98,
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
