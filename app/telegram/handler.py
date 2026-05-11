from __future__ import annotations

from pathlib import Path

from app.models.types import ClarificationRequest, StructuredIntake
from app.orchestrator.shopping_orchestrator import ShoppingOrchestrator
from app.parser.intent_parser import IntentParser
from app.storage.db import connect, initialize_schema
from app.storage.repository import Repository


# Single-user installs reuse one conversation key. When Babji starts forwarding a
# Telegram chat_id, the caller can pass it through `handle_message(text, conversation_key=...)`.
DEFAULT_CONVERSATION_KEY = "default"


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

    def handle_message(self, text: str, conversation_key: str = DEFAULT_CONVERSATION_KEY) -> dict:
        # Try to resume a clarification from a previous turn (which may have happened in
        # a different `TelegramHandler` instance — `integration_runner.handle_text`
        # constructs a fresh handler per Babji invocation, so any in-memory state would
        # be lost. State lives in `pending_clarifications` keyed by `conversation_key`.
        intake, resumed_clarification = self._resume_persisted_clarification(text, conversation_key)
        if intake is None:
            intake = self.parser.parse_structured(text)

        result = self.orchestrator.execute_structured(intake)
        payload = {
            "intent_type": result.intent_type,
            "category": result.category,
            "source_mode": intake.parsed_intent.filters.get("source_mode"),
            "message": result.message,
            "budget_summary": result.budget_summary,
            "lane_summary": result.budget_summary.get("lane_summary") if result.budget_summary else None,
            "needs_clarification": False,
        }

        if result.needs_clarification and result.clarification is not None:
            self._persist_clarification(text, result.clarification, conversation_key)
            payload["needs_clarification"] = True
            payload["clarification"] = {
                "kind": result.clarification.kind,
                "question": result.clarification.question,
                "options": result.clarification.options,
                "product_hint": result.clarification.product_hint,
                "expected_attribute": result.clarification.expected_attribute,
                "context": result.clarification.context,
            }
        elif resumed_clarification:
            # We successfully consumed a pending clarification. The persisted record was
            # already deleted inside `_resume_persisted_clarification`, so nothing else
            # to do here. (Don't clear here unconditionally — that would silently throw
            # away a valid pending clarification when the user sends an off-topic message
            # while still mid-clarification.)
            pass

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

        # Surface adapter telemetry so it's visible from the Telegram path; the formatter
        # ignores it for normal output but keeps it on the JSON payload for debugging.
        registry = getattr(self.orchestrator, "registry", None)
        if registry is not None and getattr(registry, "last_telemetry", None):
            payload["adapter_telemetry"] = list(registry.last_telemetry)

        return payload

    def _resume_persisted_clarification(
        self,
        text: str,
        conversation_key: str,
    ) -> tuple[StructuredIntake | None, bool]:
        """Returns (intake_or_none, did_resume).

        `did_resume=True` means we consumed a pending clarification and the persisted
        record was deleted. `did_resume=False` means either no pending clarification
        existed, OR there was one but the user's message didn't satisfy it (in which
        case the persisted record stays put for the next turn).
        """
        record = self.repository.load_pending_clarification(conversation_key)
        if record is None:
            return None, False
        clarification = ClarificationRequest(
            kind=record["clarification_kind"],
            question=record["question"],
            options=record.get("options") or [],
            product_hint=record.get("product_hint"),
            expected_attribute=record.get("expected_attribute"),
            context=record.get("context") or {},
        )
        original_query = record.get("raw_query") or ""
        resumed_query = self._build_resumed_query(text, clarification, original_query)
        if resumed_query is None:
            return None, False
        self.repository.clear_pending_clarification(conversation_key)
        return self.parser.parse_structured(resumed_query), True

    def _persist_clarification(
        self,
        raw_query: str,
        clarification: ClarificationRequest,
        conversation_key: str,
    ) -> None:
        self.repository.save_pending_clarification(
            conversation_key=conversation_key,
            raw_query=raw_query,
            clarification_kind=clarification.kind,
            question=clarification.question,
            options=clarification.options,
            product_hint=clarification.product_hint,
            expected_attribute=clarification.expected_attribute,
            context=clarification.context,
        )

    def _build_resumed_query(
        self,
        text: str,
        clarification: ClarificationRequest,
        original_query: str,
    ) -> str | None:
        answer = " ".join(text.lower().split())
        if clarification.kind == "product_type":
            if any(token in answer for token in ["earbuds", "earbud"]):
                return f"{original_query} earbuds"
            if any(token in answer for token in ["over-ear", "over ear", "headphones", "headphone"]):
                return f"{original_query} headphones"
            return None
        if clarification.kind == "size":
            size = self.parser._extract_size(text)
            if size is None and answer.isdigit():
                size = f"{answer} inch"
            if size is None:
                return None
            return f"{original_query} {size}"
        return None

    def close(self) -> None:
        self.conn.close()
