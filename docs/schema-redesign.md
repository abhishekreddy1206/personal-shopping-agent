# Shopping Agent Schema Redesign

## Goals
- Cleanly separate raw user input from structured intent.
- Cleanly separate product identity from offer evidence.
- Make alerting and learning auditable.
- Keep trust, confidence, and source roles explicit.
- Support deterministic core logic with agentic interpretation at the edges.

## Core entities

### 1. UserQuery
Represents the raw user request.

Fields:
- `query_id`
- `created_at`
- `raw_text`
- `channel`
- `surface`
- `request_type`
- `source_mode_requested`
- `parse_status`
- `parser_version`

### 2. ParsedIntent
Represents the deterministic parse of the request.

Fields:
- `intent_id`
- `query_id`
- `intent_type`
- `category`
- `category_confidence`
- `query_shape`
- `condition_preference`
- `urgency`
- `budget_min`
- `budget_max`
- `target_price`
- `preferred_retailers_json`
- `excluded_retailers_json`
- `notes`

### 3. ProductIntent
Represents the intended product subject.

Fields:
- `product_intent_id`
- `intent_id`
- `freeform_product_text`
- `brand`
- `product_family`
- `model_number`
- `variant`
- `size`
- `color`
- `category`
- `attributes_json`
- `canonicalization_status`
- `canonicalization_confidence`

### 4. WatchRule
Represents a persistent tracking rule.

Fields:
- `watch_rule_id`
- `product_intent_id`
- `user_label`
- `target_price`
- `target_drop_percent`
- `condition_required`
- `source_mode`
- `preferred_sources_json`
- `check_frequency`
- `priority`
- `active`
- `created_at`
- `updated_at`

### 5. SourceRecord
Represents a source definition.

Fields:
- `source_name`
- `source_role`
- `trust_tier`
- `enabled`
- `supports_live_fetch`
- `supports_marketplace_seller_model`
- `supports_coupon_enrichment`

### 6. EvidenceSnapshot
Represents raw fetched evidence.

Fields:
- `snapshot_id`
- `source_name`
- `captured_at`
- `query_id`
- `storage_path`
- `content_type`
- `capture_method`
- `sanitized`
- `retention_policy`
- `content_hash`

### 7. OfferEvidence
Represents an extracted offer candidate.

Fields:
- `offer_id`
- `query_id`
- `product_intent_id`
- `source_name`
- `source_role`
- `lane`
- `listing_url`
- `retailer`
- `seller_name`
- `condition`
- `availability`
- `base_price`
- `shipping_price`
- `tax_estimate`
- `effective_price`
- `currency`
- `coupon_code`
- `coupon_confidence`
- `seller_confidence`
- `extraction_confidence`
- `verification_state`
- `snapshot_id`
- `raw_extraction_notes`

### 8. RankedRecommendation
Represents a ranked output candidate.

Fields:
- `recommendation_id`
- `query_id`
- `offer_id`
- `rank`
- `lane`
- `score`
- `score_breakdown_json`
- `recommendation_label`
- `eligible_for_default_display`
- `eligible_for_alerting`

### 9. AlertDecision
Represents whether an alert should be sent or suppressed.

Fields:
- `alert_decision_id`
- `watch_rule_id`
- `offer_id`
- `decision_type`
- `reason`
- `decision_confidence`
- `dedupe_key`
- `created_at`

### 10. LearningSignal
Represents observed or explicit feedback.

Fields:
- `signal_id`
- `signal_type`
- `query_id`
- `watch_rule_id`
- `offer_id`
- `source_name`
- `value`
- `recorded_at`
- `context_json`

### 11. LearnedPreference
Represents bounded, explainable learned behavior.

Fields:
- `preference_id`
- `preference_key`
- `category`
- `value_json`
- `weight`
- `evidence_count`
- `updated_at`
- `learning_version`

## Entity separation rules
- `UserQuery` stores raw text only.
- `ParsedIntent` stores deterministic structured interpretation.
- `ProductIntent` stores product identity and canonicalization.
- `WatchRule` stores persistent tracking logic.
- `OfferEvidence` stores extracted source claims.
- `RankedRecommendation` stores display/alert eligibility decisions.
- `AlertDecision` stores final send/suppress outcomes.
- `LearningSignal` and `LearnedPreference` store bounded adaptation signals.
