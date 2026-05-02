from __future__ import annotations

from pathlib import Path

from app.orchestrator.shopping_orchestrator import ShoppingOrchestrator
from app.parser.intent_parser import IntentParser
from app.storage.db import connect, initialize_schema
from app.storage.repository import Repository


class TelegramHandler:
    def __init__(self, db_path: str | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        resolved_db_path = Path(db_path) if db_path else root / "data" / "db" / "shopping_agent.db"
        schema_path = root / "data" / "db" / "schema.sql"
        self.conn = connect(resolved_db_path)
        initialize_schema(self.conn, schema_path)
        self.repository = Repository(self.conn)
        self.parser = IntentParser()
        self.orchestrator = ShoppingOrchestrator(self.repository)

    def handle_message(self, text: str) -> dict:
        intake = self.parser.parse_structured(text)
        result = self.orchestrator.execute_structured(intake)
        payload = {
            "intent_type": result.intent_type,
            "category": result.category,
            "source_mode": intake.parsed_intent.filters.get("source_mode"),
            "message": result.message,
            "budget_summary": result.budget_summary,
        }
        if result.ranked_offers:
            payload["results"] = [
                {
                    "title": item.offer.title,
                    "retailer": item.offer.retailer,
                    "score": item.score,
                    "label": item.label,
                    "effective_price": item.offer.effective_price,
                    "confidence": item.offer.metadata.get("confidence") or item.offer.extraction_confidence,
                    "source_mode": item.offer.metadata.get("source_mode"),
                    "has_snapshot": bool(item.offer.evidence_snapshot and item.offer.evidence_snapshot.storage_path),
                    "lane": item.offer.metadata.get("lane"),
                    "requested_mode": item.offer.metadata.get("source_mode_requested"),
                    "source_role": item.offer.source_role,
                    "verification_state": item.offer.verification_state,
                    "condition": item.offer.condition,
                    "condition_display": item.offer.metadata.get("condition_display"),
                    "enrichment": item.offer.metadata.get("enrichment"),
                    "price_is_placeholder": item.offer.metadata.get("price_is_placeholder", False),
                    "pricing_note": item.offer.metadata.get("pricing_note"),
                    "reasons": item.reasons,
                }
                for item in result.ranked_offers
            ]
        if result.recent_searches:
            payload["recent_searches"] = result.recent_searches
        if result.watch_items:
            payload["watch_items"] = result.watch_items
        if result.alerts:
            payload["alerts"] = result.alerts
        return payload

    def close(self) -> None:
        self.conn.close()
