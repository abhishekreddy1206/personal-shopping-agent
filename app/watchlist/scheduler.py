from __future__ import annotations

from app.models.types import ParsedIntent
from app.ranking.ranker import Ranker
from app.sources.registry import SourceRegistry
from app.storage.repository import Repository


# Quick keyword inference for legacy watch items that don't have `rule_category` populated
# (created before the additive migration). New watch items always carry `rule_category`.
_ELECTRONICS_KEYWORDS = (
    "monitor", "laptop", "headphones", "headphone", "earbuds", "earbud", "tv",
    "speaker", "soundbar", "phone", "tablet", "camera", "amplifier", "receiver",
)
_CLOTHES_KEYWORDS = ("nike", "adidas", "shoe", "shoes", "sneaker", "running", "jacket", "hoodie")


class WatchlistScheduler:
    """Run scheduled checks for active watch items, honoring each rule's source_mode/category."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        self.registry = SourceRegistry()
        self.ranker = Ranker()

    def run_pending_checks(self) -> list[dict]:
        results = []
        for item in self.repository.list_active_watch_items():
            query = item["normalized_subject"] or item["user_label"]
            category = item.get("rule_category") or self._infer_category(query)
            source_mode = item.get("rule_source_mode") or "trusted_plus_discovery"
            condition_pref = item.get("rule_condition_required") or "any"

            intent = ParsedIntent(
                intent_type="watch_check",
                raw_query=query,
                category=category,
                product_terms=query.split(),
                condition_preference=condition_pref,
                filters={"source_mode": source_mode, "product_text": query},
            )
            offers = self.registry.search(intent)
            ranked = self.ranker.rank(self._filter_offers(offers)) if offers else []
            best = ranked[0] if ranked else None
            offer_id = None
            alerts = []
            if best is not None:
                offer_id = self.repository.add_offer(best.offer)
                self.repository.add_price_observation(
                    watch_item_id=item["id"],
                    offer_id=offer_id,
                    effective_price=best.offer.effective_price,
                    availability=best.offer.availability,
                    trend_context={
                        "label": best.label,
                        "reasons": best.reasons,
                        "confidence": best.offer.metadata.get("confidence"),
                        "source_mode": best.offer.metadata.get("source_mode"),
                    },
                )
                target_price = item.get("target_price")
                confidence = best.offer.metadata.get("confidence")
                if (
                    target_price is not None
                    and best.offer.effective_price is not None
                    and best.offer.effective_price <= target_price
                    and confidence in ("medium", "high")
                ):
                    alerts.append(
                        {
                            "type": "below_target_price",
                            "message": "Price is now at or below target.",
                            "target_price": target_price,
                            "current_price": best.offer.effective_price,
                        }
                    )
            results.append(
                {
                    "watch_item_id": item["id"],
                    "query": item["user_label"],
                    "normalized_subject": item.get("normalized_subject"),
                    "category": category,
                    "source_mode": source_mode,
                    "best_offer": {
                        "retailer": best.offer.retailer,
                        "title": best.offer.title,
                        "effective_price": best.offer.effective_price,
                        "confidence": best.offer.metadata.get("confidence"),
                        "source_mode": best.offer.metadata.get("source_mode"),
                    } if best else None,
                    "alerts": alerts,
                    "adapter_telemetry": list(getattr(self.registry, "last_telemetry", []) or []),
                }
            )
        return results

    def _infer_category(self, query: str) -> str | None:
        lowered = (query or "").lower()
        if any(term in lowered for term in _ELECTRONICS_KEYWORDS):
            return "electronics"
        if any(term in lowered for term in _CLOTHES_KEYWORDS):
            return "clothes_shoes"
        return None

    def _filter_offers(self, offers):
        filtered = []
        for offer in offers:
            confidence = offer.metadata.get("confidence")
            price = offer.effective_price
            if confidence == "low":
                continue
            if price is not None and price < 20:
                continue
            filtered.append(offer)
        return filtered
