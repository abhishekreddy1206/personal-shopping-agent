from __future__ import annotations

from app.models.types import ParsedIntent
from app.ranking.ranker import Ranker
from app.sources.registry import SourceRegistry
from app.storage.repository import Repository


class WatchlistScheduler:
    """Basic scheduled check coordinator for active watch items."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        self.registry = SourceRegistry()
        self.ranker = Ranker()

    def run_pending_checks(self) -> list[dict]:
        results = []
        for item in self.repository.list_active_watch_items():
            query = item["normalized_subject"] or item["user_label"]
            category = "electronics" if any(term in query.lower() for term in ["monitor", "laptop", "headphones"]) else None
            intent = ParsedIntent(
                intent_type="watch_check",
                raw_query=query,
                category=category,
                product_terms=query.split(),
                filters={"source_mode": "trusted_plus_discovery"},
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
                    "best_offer": {
                        "retailer": best.offer.retailer,
                        "title": best.offer.title,
                        "effective_price": best.offer.effective_price,
                        "confidence": best.offer.metadata.get("confidence"),
                        "source_mode": best.offer.metadata.get("source_mode"),
                    } if best else None,
                    "alerts": alerts,
                }
            )
        return results

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
