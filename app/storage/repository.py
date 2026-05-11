from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.models.types import EvidenceSnapshot, OfferCandidate, ParsedIntent, ProductIntent, RankedOffer, StructuredIntake, UserQuery, WatchRule


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_structured_intake(self, intake: StructuredIntake) -> dict[str, int | None]:
        user_query_id = self._create_user_query(intake.user_query)
        parsed_intent_id = self._create_parsed_intent(user_query_id, intake.parsed_intent)
        product_intent_id = self._create_product_intent(parsed_intent_id, intake.product_intent)
        watch_rule_id = None
        if intake.watch_rule is not None:
            watch_rule_id = self._create_or_get_watch_rule(
                product_intent_id,
                intake.watch_rule,
                category=intake.product_intent.category or intake.parsed_intent.category,
            )
        return {
            "user_query_id": user_query_id,
            "parsed_intent_id": parsed_intent_id,
            "product_intent_id": product_intent_id,
            "watch_rule_id": watch_rule_id,
        }

    def _create_user_query(self, user_query: UserQuery) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO user_queries (
                created_at, raw_text, channel, surface, request_type,
                source_mode_requested, parse_status, parser_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                utc_now(),
                user_query.raw_text,
                user_query.channel,
                user_query.surface,
                user_query.request_type,
                user_query.source_mode_requested,
                user_query.parse_status,
                user_query.parser_version,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def _create_parsed_intent(self, user_query_id: int, intent: ParsedIntent) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO parsed_intents (
                user_query_id, created_at, intent_type, category, category_confidence,
                query_shape, condition_preference, urgency, budget_min, budget_max,
                target_price, product_terms_json, filters_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_query_id,
                utc_now(),
                intent.intent_type,
                intent.category,
                intent.category_confidence,
                intent.query_shape,
                intent.condition_preference,
                intent.urgency,
                intent.budget_min,
                intent.budget_max,
                intent.target_price,
                json.dumps(intent.product_terms),
                json.dumps(intent.filters),
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def _create_product_intent(self, parsed_intent_id: int, product_intent: ProductIntent) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO product_intents (
                parsed_intent_id, created_at, freeform_product_text, brand,
                product_family, model_number, variant, size, color, category,
                attributes_json, canonicalization_status, canonicalization_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parsed_intent_id,
                utc_now(),
                product_intent.freeform_product_text,
                product_intent.brand,
                product_intent.product_family,
                product_intent.model_number,
                product_intent.variant,
                product_intent.size,
                product_intent.color,
                product_intent.category,
                json.dumps(product_intent.attributes),
                product_intent.canonicalization_status,
                product_intent.canonicalization_confidence,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def _find_watch_rule(self, normalized_subject: str, target_price: float | None) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT id, normalized_subject, user_label, target_price, source_mode, check_frequency, priority, active, notes
            FROM watch_rules
            WHERE active = 1 AND normalized_subject = ? AND (
              (target_price IS NULL AND ? IS NULL) OR target_price = ?
            )
            ORDER BY id DESC
            LIMIT 1
            """,
            (normalized_subject, target_price, target_price),
        ).fetchone()
        return dict(row) if row else None

    def _create_or_get_watch_rule(self, product_intent_id: int, watch_rule: WatchRule, category: str | None = None) -> int:
        existing = self._find_watch_rule(watch_rule.normalized_subject, watch_rule.target_price)
        if existing is not None:
            return int(existing["id"])
        cursor = self.conn.execute(
            """
            INSERT INTO watch_rules (
                product_intent_id, created_at, updated_at, normalized_subject, user_label,
                target_price, target_drop_percent, condition_required, source_mode,
                category, preferred_sources_json, check_frequency, priority, active, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_intent_id,
                utc_now(),
                utc_now(),
                watch_rule.normalized_subject,
                watch_rule.user_label,
                watch_rule.target_price,
                watch_rule.target_drop_percent,
                watch_rule.condition_required,
                watch_rule.source_mode,
                category,
                json.dumps(watch_rule.preferred_sources),
                watch_rule.check_frequency,
                watch_rule.priority,
                1 if watch_rule.active else 0,
                watch_rule.notes,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def create_search_request(self, intent: ParsedIntent) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO search_requests (
                created_at, raw_query, intent_type, category,
                budget_min, budget_max, urgency, filters_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                utc_now(),
                intent.raw_query,
                intent.intent_type,
                intent.category,
                intent.budget_min,
                intent.budget_max,
                intent.urgency or intent.filters.get("urgency"),
                json.dumps(intent.filters),
                "created",
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def update_search_request_status(self, search_request_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE search_requests SET status = ? WHERE id = ?",
            (status, search_request_id),
        )
        self.conn.commit()

    def create_search_result(self, search_request_id: int, canonical_query: str, notes: str = "") -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO search_results (search_request_id, created_at, canonical_query, summary_json, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (search_request_id, utc_now(), canonical_query, json.dumps({}), notes),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def update_search_result_summary(self, search_result_id: int, summary: dict[str, Any], notes: str = "") -> None:
        self.conn.execute(
            "UPDATE search_results SET summary_json = ?, notes = ? WHERE id = ?",
            (json.dumps(summary), notes, search_result_id),
        )
        self.conn.commit()

    def add_evidence_snapshot(self, snapshot: EvidenceSnapshot | None) -> int | None:
        if snapshot is None:
            return None
        cursor = self.conn.execute(
            """
            INSERT INTO evidence_snapshots (
                created_at, source_name, storage_path, content_type, capture_method,
                sanitized, retention_policy, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                utc_now(),
                snapshot.source_name,
                snapshot.storage_path,
                snapshot.content_type,
                snapshot.capture_method,
                1 if snapshot.sanitized else 0,
                snapshot.retention_policy,
                snapshot.content_hash,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def add_offer_evidence(self, offer: OfferCandidate, snapshot_id: int | None) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO offer_evidence (
                created_at, source_name, source_role, lane, retailer, seller_name,
                listing_url, title, condition, availability, base_price, shipping_price,
                effective_price, coupon_confidence, extraction_confidence,
                verification_state, evidence_snapshot_id, raw_extraction_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                utc_now(),
                offer.source_name,
                offer.source_role,
                offer.metadata.get("lane", "trusted_retail"),
                offer.retailer,
                offer.metadata.get("seller_name"),
                offer.listing_url,
                offer.title,
                offer.condition,
                offer.availability,
                offer.base_price,
                offer.shipping_price,
                offer.effective_price,
                offer.metadata.get("coupon_confidence"),
                offer.extraction_confidence,
                offer.verification_state,
                snapshot_id,
                offer.metadata.get("raw_extraction_notes"),
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def add_offer(self, offer: OfferCandidate) -> int:
        snapshot_id = self.add_evidence_snapshot(offer.evidence_snapshot)
        offer_evidence_id = self.add_offer_evidence(offer, snapshot_id)
        raw_payload_path = offer.metadata.get("snapshot_path") if offer.metadata else None
        cursor = self.conn.execute(
            """
            INSERT INTO offers (
                offer_evidence_id, source_name, retailer, listing_url, title, condition,
                availability, base_price, shipping_price, effective_price, captured_at, raw_payload_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                offer_evidence_id,
                offer.source_name,
                offer.retailer,
                offer.listing_url,
                offer.title,
                offer.condition,
                offer.availability,
                offer.base_price,
                offer.shipping_price,
                offer.effective_price,
                utc_now(),
                raw_payload_path,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def link_ranked_offer(self, search_result_id: int, offer_id: int, ranked_offer: RankedOffer, rank: int) -> None:
        self.conn.execute(
            """
            INSERT INTO search_result_offers (search_result_id, offer_id, rank, score, label, reason_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                search_result_id,
                offer_id,
                rank,
                ranked_offer.score,
                ranked_offer.label,
                json.dumps(ranked_offer.reasons),
            ),
        )
        self.conn.commit()

    def list_recent_searches(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, created_at, raw_query, intent_type, category, status
            FROM search_requests
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def find_active_watch_item(self, normalized_subject: str, target_price: float | None) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT id, created_at, user_label, normalized_subject, target_price, check_frequency, active, notes, watch_rule_id
            FROM watch_items
            WHERE active = 1 AND normalized_subject = ? AND (
              (target_price IS NULL AND ? IS NULL) OR target_price = ?
            )
            ORDER BY id DESC
            LIMIT 1
            """,
            (normalized_subject, target_price, target_price),
        ).fetchone()
        return dict(row) if row else None

    def create_watch_item(self, intake: StructuredIntake) -> tuple[int, bool]:
        watch_rule = intake.watch_rule
        if watch_rule is None:
            raise ValueError("Watch rule required for watch item creation")
        existing = self.find_active_watch_item(watch_rule.normalized_subject, watch_rule.target_price)
        if existing is not None:
            return int(existing["id"]), False
        watch_rule_id = self._create_or_get_watch_rule(0, watch_rule)
        cursor = self.conn.execute(
            """
            INSERT INTO watch_items (
                watch_rule_id, created_at, user_label, normalized_subject, target_price,
                target_drop_percent, preferred_sources_json, check_frequency, active, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                watch_rule_id,
                utc_now(),
                watch_rule.user_label,
                watch_rule.normalized_subject,
                watch_rule.target_price,
                watch_rule.target_drop_percent,
                json.dumps(watch_rule.preferred_sources),
                watch_rule.check_frequency,
                watch_rule.notes,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid), True

    def list_watch_items(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, created_at, user_label, normalized_subject, target_price, check_frequency, active, notes, watch_rule_id
            FROM watch_items
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_active_watch_items(self) -> list[dict[str, Any]]:
        # Join the linked watch_rule so the scheduler can honor the original `source_mode`
        # and `category` instead of guessing from the label string. See docs/flow-audit.md
        # Issue 5: previously the scheduler hardcoded mode/category and silently produced
        # zero offers for any non-electronics watch.
        rows = self.conn.execute(
            """
            SELECT
                wi.id, wi.created_at, wi.user_label, wi.normalized_subject,
                wi.target_price, wi.check_frequency, wi.active, wi.notes, wi.watch_rule_id,
                wr.source_mode AS rule_source_mode,
                wr.category AS rule_category,
                wr.condition_required AS rule_condition_required
            FROM watch_items wi
            LEFT JOIN watch_rules wr ON wr.id = wi.watch_rule_id
            WHERE wi.active = 1
            ORDER BY wi.id DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def save_pending_clarification(
        self,
        conversation_key: str,
        raw_query: str,
        clarification_kind: str,
        question: str,
        options: list[str],
        product_hint: str | None,
        expected_attribute: str | None,
        context: dict[str, Any],
    ) -> None:
        """Store the latest unresolved clarification for a conversation. Overwrites
        any prior pending clarification for the same `conversation_key` so a fresh
        clarification supersedes a stale one. Used by TelegramHandler to survive the
        per-call handler reconstruction inside `integration_runner.handle_text` —
        without this, the second Telegram turn never sees the first turn's question.
        """
        # INSERT OR REPLACE instead of ON CONFLICT(...) DO UPDATE: the latter is UPSERT
        # syntax that requires SQLite >= 3.24.0 (June 2018). Some Python builds still ship
        # older SQLite (e.g. Python 3.7.2 on Windows bundles 3.21.0). Since conversation_key
        # is the PRIMARY KEY and we always rewrite every column, REPLACE has identical
        # semantics here.
        self.conn.execute(
            """
            INSERT OR REPLACE INTO pending_clarifications (
                conversation_key, created_at, raw_query, clarification_kind, question,
                options_json, product_hint, expected_attribute, context_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_key,
                utc_now(),
                raw_query,
                clarification_kind,
                question,
                json.dumps(options),
                product_hint,
                expected_attribute,
                json.dumps(context),
            ),
        )
        self.conn.commit()

    def load_pending_clarification(self, conversation_key: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM pending_clarifications WHERE conversation_key = ?",
            (conversation_key,),
        ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["options"] = json.loads(record.pop("options_json") or "[]")
        record["context"] = json.loads(record.pop("context_json") or "{}")
        return record

    def clear_pending_clarification(self, conversation_key: str) -> None:
        self.conn.execute(
            "DELETE FROM pending_clarifications WHERE conversation_key = ?",
            (conversation_key,),
        )
        self.conn.commit()

    def add_price_observation(self, watch_item_id: int, offer_id: int | None, effective_price: float | None, availability: str | None, trend_context: dict[str, Any]) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO price_observations (watch_item_id, offer_id, observed_at, effective_price, availability, trend_context_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                watch_item_id,
                offer_id,
                utc_now(),
                effective_price,
                availability,
                json.dumps(trend_context),
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)
