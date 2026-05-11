from __future__ import annotations

from pathlib import Path

from app.formatting import format_result
from app.models.types import EvidenceSnapshot, OfferCandidate, ParsedIntent, ProductIntent, StructuredIntake, UserQuery
from app.orchestrator.shopping_orchestrator import ShoppingOrchestrator
from app.parser.intent_parser import IntentParser
from app.telegram.handler import TelegramHandler
from app.storage.db import connect, initialize_schema
from app.storage.repository import Repository


class StubRegistry:
    def __init__(self, offers: list[OfferCandidate]) -> None:
        self._offers = offers

    def search(self, intent: ParsedIntent) -> list[OfferCandidate]:
        return list(self._offers)


def make_offer(title: str, price: float | None, retailer: str = "Nike") -> OfferCandidate:
    return OfferCandidate(
        source_name="stub",
        retailer=retailer,
        listing_url="https://example.com/item",
        title=title,
        effective_price=price,
        base_price=price,
        shipping_price=0.0 if price is not None else None,
        condition="new",
        availability="in_stock",
        metadata={"lane": "trusted_retail", "source_mode": "live_extract"},
        evidence_snapshot=EvidenceSnapshot(source_name="stub", storage_path="snapshot.txt"),
        source_role="truth",
        verification_state="partially_verified",
        extraction_confidence="medium",
    )


def make_intake(query: str, budget_max: float | None) -> StructuredIntake:
    intent = ParsedIntent(
        intent_type="search",
        raw_query=query,
        category="clothes_shoes",
        budget_max=budget_max,
        filters={"source_mode": "trusted_plus_discovery", "product_text": query},
    )
    return StructuredIntake(
        user_query=UserQuery(raw_text=query),
        parsed_intent=intent,
        product_intent=ProductIntent(freeform_product_text=query, category="clothes_shoes"),
    )


ROOT = Path(__file__).resolve().parents[1]


def build_orchestrator(tmp_path) -> ShoppingOrchestrator:
    db_path = tmp_path / "shopping.db"
    conn = connect(db_path)
    initialize_schema(conn, ROOT / "data" / "db" / "schema.sql")
    return ShoppingOrchestrator(Repository(conn))


def test_orchestrator_filters_out_of_budget_results(tmp_path) -> None:
    orchestrator = build_orchestrator(tmp_path)
    orchestrator.registry = StubRegistry(
        [
            make_offer("Nike Pegasus 41", 119.99),
            make_offer("Nike Structure 26", 190.0),
            make_offer("Nike Vomero Premium", 230.0),
        ]
    )

    result = orchestrator.execute_structured(make_intake("Best men's running shoes under 120", 120.0))

    assert [item.offer.title for item in result.ranked_offers] == ["Nike Pegasus 41"]
    assert result.budget_summary["over_budget_count"] == 2
    assert result.message == "Found 1 results within your $120 budget."


def test_orchestrator_returns_no_results_when_everything_is_over_budget(tmp_path) -> None:
    orchestrator = build_orchestrator(tmp_path)
    orchestrator.registry = StubRegistry(
        [
            make_offer("Nike ACG Zegama Coming Soon", 180.0),
            make_offer("Nike Structure 26", 190.0),
            make_offer("Nike Vomero Premium Best Seller", 230.0),
        ]
    )

    result = orchestrator.execute_structured(make_intake("Best men's running shoes under 120", 120.0))

    assert result.ranked_offers == []
    assert result.budget_summary["within_budget_count"] == 0
    assert result.budget_summary["lowest_over_budget"]["effective_price"] == 180.0
    assert "No results found within your $120 budget" in result.message
    formatted = format_result({"message": result.message, "budget_summary": result.budget_summary, "source_mode": "trusted_plus_discovery"})
    assert "Closest over budget: Nike ACG Zegama Coming Soon — Nike — $180.0" in formatted


def test_handler_smoke_query_does_not_surface_over_budget_results(tmp_path) -> None:
    """Force the registry to return only over-budget offers and verify the handler
    correctly hides them. Previously this test relied on the real Nike network plus
    the (now-removed) blanket stub-drop policy; we now stub the registry so the test
    is deterministic and doesn't depend on Nike's HTML staying parseable.
    """
    db_path = tmp_path / "handler.db"
    handler = TelegramHandler(db_path=str(db_path))
    handler.orchestrator.registry = StubRegistry(
        [
            make_offer("Nike Vaporfly", 250.0),
            make_offer("Nike Alphafly", 285.0),
        ]
    )
    try:
        payload = handler.handle_message("Best men's running shoes under 120")
    finally:
        handler.close()

    assert payload["budget_summary"]["applied"] is True
    assert payload["message"].startswith("No results found within your $120 budget")
    assert "results" not in payload


def test_orchestrator_returns_clarification_without_searching(tmp_path) -> None:
    orchestrator = build_orchestrator(tmp_path)
    intake = IntentParser().parse_structured("Find me a good deal on Bose QuietComfort Ultra 2")

    result = orchestrator.execute_structured(intake)

    assert result.needs_clarification is True
    assert result.clarification is not None
    assert result.clarification.kind == "product_type"
    assert result.ranked_offers == []


def test_handler_resumes_bose_clarification_with_short_answer(tmp_path) -> None:
    db_path = tmp_path / "clarification-bose.db"
    handler = TelegramHandler(db_path=str(db_path))
    try:
        first = handler.handle_message("Find me a good deal on Bose QuietComfort Ultra 2")
        second = handler.handle_message("earbuds")
    finally:
        handler.close()

    assert first["needs_clarification"] is True
    assert first["clarification"]["kind"] == "product_type"
    assert second["needs_clarification"] is False
    assert second["source_mode"] == "trusted_plus_discovery"


def test_handler_resumes_frame_size_clarification_with_short_answer(tmp_path) -> None:
    db_path = tmp_path / "clarification-frame.db"
    handler = TelegramHandler(db_path=str(db_path))
    try:
        first = handler.handle_message("Find me the best deal on Samsung The Frame TV")
        second = handler.handle_message("55 inch")
    finally:
        handler.close()

    assert first["needs_clarification"] is True
    assert first["clarification"]["kind"] == "size"
    assert second["needs_clarification"] is False
    assert second["message"]
    assert second["source_mode"] == "trusted_plus_discovery"
