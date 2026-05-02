from __future__ import annotations

from app.models.types import OfferCandidate, RankedOffer


class Ranker:
    """Rank with trust/lane awareness before price, while still surfacing low-confidence lanes honestly."""

    LANE_PRIORITY = {
        "trusted_retail": 0,
        "discovery": 2,
        "marketplace": 3,
    }
    VERIFICATION_PRIORITY = {
        "verified": 0,
        "partially_verified": 1,
        "unverified": 2,
        "signal_only": 3,
        "seller_unverified": 4,
    }
    CONDITION_PRIORITY = {
        "new": 0,
        "refurbished": 1,
        "open_box": 2,
        "used": 3,
        "unknown": 4,
        None: 4,
    }

    def rank(self, offers: list[OfferCandidate]) -> list[RankedOffer]:
        def sort_key(offer: OfferCandidate) -> tuple:
            price = offer.effective_price if offer.effective_price is not None else 10**9
            lane = offer.metadata.get("lane") or offer.metadata.get("source_family") or "trusted_retail"
            match_penalty = 1 - float(offer.metadata.get("match_score", 0))
            exact_model_penalty = 0 if offer.metadata.get("exact_model_match") else 1
            generic_penalty = 1 if offer.metadata.get("generic_result") else 0
            unknown_price_penalty = 1 if offer.effective_price is None else 0
            discovery_penalty = 1 if lane == "discovery" else 0
            marketplace_penalty = 1 if lane == "marketplace" else 0
            stub_penalty = 1 if offer.metadata.get("source_mode") == "fallback_stub" else 0
            return (
                self.LANE_PRIORITY.get(lane, 9),
                stub_penalty,
                marketplace_penalty,
                discovery_penalty,
                self.CONDITION_PRIORITY.get(offer.condition, 4),
                exact_model_penalty,
                generic_penalty,
                unknown_price_penalty,
                match_penalty,
                self.VERIFICATION_PRIORITY.get(offer.verification_state, 9),
                price,
                offer.retailer,
            )

        ordered = sorted(offers, key=sort_key)
        ranked: list[RankedOffer] = []
        for idx, offer in enumerate(ordered, start=1):
            label = None
            reasons = self._build_reasons(offer)
            if idx == 1 and offer.metadata.get("source_mode") == "fallback_stub":
                label = "best_fallback_stub"
            elif idx == 1 and offer.metadata.get("lane", "trusted_retail") == "trusted_retail":
                label = "best_verified_retail"
            elif idx == 1:
                label = "best_available_signal"
            ranked.append(RankedOffer(offer=offer, score=float(max(0, 100 - idx)), label=label, reasons=reasons))
        return ranked

    def _build_reasons(self, offer: OfferCandidate) -> list[str]:
        reasons = []
        lane = offer.metadata.get("lane") or "trusted_retail"
        reasons.append(f"Lane: {lane}.")
        if offer.effective_price is not None:
            reasons.append(f"Effective price: ${offer.effective_price}.")
        else:
            reasons.append("Effective price unavailable from current extraction.")
        if offer.metadata.get("match_score") is not None:
            reasons.append("Title/query match score: {}.".format(offer.metadata.get("match_score")))
        if offer.metadata.get("source_mode") == "fallback_stub":
            reasons.append("Placeholder fallback offer; price is a demo estimate until live extraction succeeds.")
        if offer.verification_state:
            reasons.append("Verification state: {}.".format(offer.verification_state))
        if offer.condition:
            reasons.append("Condition: {}.".format(offer.condition))
        if offer.source_role:
            reasons.append("Source role: {}.".format(offer.source_role))
        return reasons
