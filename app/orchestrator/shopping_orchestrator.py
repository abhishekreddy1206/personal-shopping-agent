from __future__ import annotations

from app.models.types import ExecutionResult, OfferCandidate, ParsedIntent, RankedOffer, StructuredIntake
from app.ranking.ranker import Ranker
from app.sources.registry import SourceRegistry
from app.storage.repository import Repository


class ShoppingOrchestrator:
    """Coordinates parsing, source adapters, persistence, and list retrieval."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        self.registry = SourceRegistry()
        self.ranker = Ranker()

    def execute(self, intent: ParsedIntent) -> ExecutionResult:
        raise NotImplementedError("Use execute_structured for the redesigned flow.")

    def execute_structured(self, intake: StructuredIntake) -> ExecutionResult:
        intent = intake.parsed_intent
        self.repository.create_structured_intake(intake)

        if intent.needs_clarification and intent.clarification is not None:
            return ExecutionResult(
                intent_type=intent.intent_type,
                category=intent.category,
                message=intent.clarification.question,
                needs_clarification=True,
                clarification=intent.clarification,
            )

        if intent.intent_type == "history_lookup":
            searches = self.repository.list_recent_searches()
            return ExecutionResult(
                intent_type=intent.intent_type,
                category=intent.category,
                recent_searches=searches,
                message="Retrieved recent searches.",
            )

        if intent.intent_type == "watchlist_view":
            watch_items = self.repository.list_watch_items()
            return ExecutionResult(
                intent_type=intent.intent_type,
                category=intent.category,
                watch_items=watch_items,
                message="Retrieved watchlist items.",
            )

        if intent.intent_type == "watch_create":
            search_id = self.repository.create_search_request(intent)
            watch_id, created = self.repository.create_watch_item(intake)
            note = "Watch item created" if created else "Watch item already existed"
            self.repository.create_search_result(search_id, intent.raw_query, notes=note)
            self.repository.update_search_request_status(search_id, "watch_created" if created else "watch_existing")
            watch_items = self.repository.list_watch_items()
            message = "Created watch item #{}.".format(watch_id) if created else "Already tracking watch item #{}.".format(watch_id)
            return ExecutionResult(
                intent_type=intent.intent_type,
                category=intent.category,
                watch_items=watch_items,
                message=message,
            )

        search_id = self.repository.create_search_request(intent)
        search_result_id = self.repository.create_search_result(search_id, intent.raw_query)
        ranked_offers, budget_summary = self._search_and_rank(intent)
        for rank, ranked_offer in enumerate(ranked_offers, start=1):
            offer_id = self.repository.add_offer(ranked_offer.offer)
            self.repository.link_ranked_offer(search_result_id, offer_id, ranked_offer, rank)
        summary = self._build_summary(ranked_offers, budget_summary)
        self.repository.update_search_result_summary(search_result_id, summary, notes="Search executed")
        self.repository.update_search_request_status(search_id, "completed")
        budget_summary = self._attach_lane_summary(ranked_offers, budget_summary)
        return ExecutionResult(
            intent_type=intent.intent_type,
            category=intent.category,
            ranked_offers=ranked_offers,
            budget_summary=budget_summary,
            message=self._build_message(ranked_offers, budget_summary),
        )

    def _search_and_rank(self, intent: ParsedIntent) -> tuple[list[RankedOffer], dict]:
        offers = self.registry.search(intent)
        if not offers:
            return [], self._empty_budget_summary(intent)
        constrained_offers, budget_summary = self._apply_budget_constraints(offers, intent)
        if not constrained_offers:
            return [], budget_summary
        return self.ranker.rank(constrained_offers), budget_summary

    def _apply_budget_constraints(self, offers: list[OfferCandidate], intent: ParsedIntent) -> tuple[list[OfferCandidate], dict]:
        budget_min = intent.budget_min
        budget_max = intent.budget_max
        if budget_max is None and budget_min is None:
            return offers, self._empty_budget_summary(intent)

        within_budget: list[OfferCandidate] = []
        over_budget: list[OfferCandidate] = []
        under_budget: list[OfferCandidate] = []
        unknown_price: list[OfferCandidate] = []

        for offer in offers:
            price = offer.effective_price
            if price is None:
                unknown_price.append(offer)
                continue
            if budget_min is not None and price < budget_min:
                under_budget.append(offer)
                continue
            if budget_max is not None and price > budget_max:
                over_budget.append(offer)
                continue
            within_budget.append(offer)

        summary = {
            "applied": True,
            "budget_min": budget_min,
            "budget_max": budget_max,
            "within_budget_count": len(within_budget),
            "over_budget_count": len(over_budget),
            "under_budget_count": len(under_budget),
            "unknown_price_count": len(unknown_price),
            "lowest_over_budget": self._cheapest_offer(over_budget),
            "lowest_within_budget": self._cheapest_offer(within_budget),
        }
        return within_budget, summary

    def _build_message(self, ranked_offers: list[RankedOffer], budget_summary: dict) -> str:
        if not budget_summary.get("applied"):
            lane_summary = budget_summary.get("lane_summary") or {}
            trusted = lane_summary.get("cheapest_trusted_retail")
            market = lane_summary.get("cheapest_marketplace")
            overall = lane_summary.get("best_overall_value")
            if trusted or market or overall:
                parts = []
                if trusted:
                    parts.append("cheapest trusted retail: {} at ${:.2f}".format(trusted.get("retailer"), trusted.get("effective_price")))
                if market:
                    parts.append("cheapest marketplace: {} at ${:.2f}".format(market.get("retailer"), market.get("effective_price")))
                if overall:
                    parts.append("best overall: {} at ${:.2f}".format(overall.get("retailer"), overall.get("effective_price")))
                return "Search executed and stored — {}.".format("; ".join(parts))
            return "Search executed and stored."

        budget_max = budget_summary.get("budget_max")
        if ranked_offers:
            if budget_max is not None:
                return "Found {} results within your ${:.0f} budget.".format(len(ranked_offers), budget_max)
            return "Found {} results within your requested price range.".format(len(ranked_offers))

        lowest_over_budget = budget_summary.get("lowest_over_budget") or {}
        if lowest_over_budget:
            label = lowest_over_budget.get("title") or lowest_over_budget.get("retailer") or "candidate"
            price = lowest_over_budget.get("effective_price")
            return "No results found within your ${:.0f} budget. Cheapest nearby option was {} at ${:.2f}.".format(
                budget_max,
                label,
                price,
            )
        unknown_count = budget_summary.get("unknown_price_count", 0)
        if unknown_count:
            return "No results could be confirmed within your budget because {} candidate prices were unavailable.".format(unknown_count)
        return "No results found within your requested price range."

    def _empty_budget_summary(self, intent: ParsedIntent) -> dict:
        return {
            "applied": bool(intent.budget_min is not None or intent.budget_max is not None),
            "budget_min": intent.budget_min,
            "budget_max": intent.budget_max,
            "within_budget_count": 0,
            "over_budget_count": 0,
            "under_budget_count": 0,
            "unknown_price_count": 0,
            "lowest_over_budget": None,
            "lowest_within_budget": None,
        }

    def _cheapest_offer(self, offers: list[OfferCandidate]) -> dict | None:
        priced = [offer for offer in offers if offer.effective_price is not None]
        if not priced:
            return None
        best = min(priced, key=lambda offer: (float(offer.effective_price), offer.retailer, offer.title))
        return {
            "title": best.title,
            "retailer": best.retailer,
            "effective_price": best.effective_price,
        }

    def _build_summary(self, ranked_offers: list[RankedOffer], budget_summary: dict) -> dict:
        summary = {"offer_count": len(ranked_offers), "budget": budget_summary}
        if ranked_offers:
            best = ranked_offers[0]
            summary["best_overall"] = {
                "title": best.offer.title,
                "retailer": best.offer.retailer,
                "effective_price": best.offer.effective_price,
            }
        lane_summary = budget_summary.get("lane_summary")
        if lane_summary:
            summary["lane_summary"] = lane_summary
        return summary

    def _attach_lane_summary(self, ranked_offers: list[RankedOffer], budget_summary: dict) -> dict:
        lane_summary = {
            "cheapest_trusted_retail": self._cheapest_ranked_offer_for_lane(ranked_offers, "trusted_retail"),
            "cheapest_marketplace": self._cheapest_ranked_offer_for_lane(ranked_offers, "marketplace"),
        }
        candidates = [item for item in lane_summary.values() if item]
        lane_summary["best_overall_value"] = min(candidates, key=lambda item: (item.get("effective_price"), item.get("retailer"), item.get("title"))) if candidates else None
        updated = dict(budget_summary)
        updated["lane_summary"] = lane_summary
        return updated

    def _cheapest_ranked_offer_for_lane(self, ranked_offers: list[RankedOffer], lane: str) -> dict | None:
        matches = [item for item in ranked_offers if (item.offer.metadata.get("lane") or "trusted_retail") == lane and item.offer.effective_price is not None]
        if not matches:
            return None
        best = min(matches, key=lambda item: (float(item.offer.effective_price), item.offer.retailer, item.offer.title))
        return {
            "title": best.offer.title,
            "retailer": best.offer.retailer,
            "effective_price": best.offer.effective_price,
            "lane": lane,
            "condition": best.offer.condition,
            "verification_state": best.offer.verification_state,
        }
