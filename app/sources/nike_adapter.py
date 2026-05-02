from __future__ import annotations

from app.models.types import EvidenceSnapshot, OfferCandidate, ParsedIntent


class NikeAdapter:
    name = "nike"
    category = "clothes_shoes"

    def search(self, intent: ParsedIntent) -> list[OfferCandidate]:
        title = " ".join(intent.product_terms) or intent.raw_query
        return [
            OfferCandidate(
                source_name=self.name,
                retailer="Nike",
                listing_url="https://www.nike.com/w?q=" + title.replace(" ", "%20"),
                title=title + " — Nike candidate",
                base_price=119.99,
                shipping_price=0.0,
                effective_price=119.99,
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
