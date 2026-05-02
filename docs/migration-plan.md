# Migration Plan to Revised Schema

## Goal
Move from the current lightweight SQLite schema to the redesigned structured model without losing core search and watch history.

## Current-to-target mapping

### Current `search_requests`
Map to:
- `UserQuery`
- partial `ParsedIntent`

### Current `search_results`
Map to:
- `RankedRecommendation` summaries
- transitional query result metadata

### Current `canonical_products`
Replace with:
- `ProductIntent`

### Current `offers`
Map to:
- `OfferEvidence`

### Current `search_result_offers`
Map to:
- `RankedRecommendation`

### Current `watch_items`
Map to:
- `WatchRule`

### Current `price_observations`
Can remain as observation history, but should later reference:
- `WatchRule`
- `OfferEvidence`
- `AlertDecision` when relevant

### Current `alert_events`
Replace or extend into:
- `AlertDecision`

### Current `feedback_signals`
Map to:
- `LearningSignal`

### Current `learned_preferences`
Keep conceptually, but align to:
- `LearnedPreference`

## Migration phases

### Phase 1 — additive schema
- Add new tables alongside existing tables.
- Do not immediately delete current tables.
- Keep current flows running while dual-writing selected fields.

### Phase 2 — parser and watch-rule migration
- Update parser to write `UserQuery`, `ParsedIntent`, and `ProductIntent`.
- Update watch creation to write `WatchRule` instead of raw watch blobs.

### Phase 3 — evidence/ranking migration
- Update search adapters to write `EvidenceSnapshot` and `OfferEvidence`.
- Update ranking to write `RankedRecommendation`.

### Phase 4 — alert migration
- Update watch-check flow to generate `AlertDecision` records before message formatting.
- Add dedupe-key enforcement.

### Phase 5 — learning migration
- Replace ad hoc feedback writes with structured `LearningSignal`.
- Update preference updates to use `LearnedPreference` consistently.

### Phase 6 — deprecation
- Freeze writes to old tables.
- Validate parity.
- Remove or archive obsolete tables only after confidence is high.

## Data safety rules
- Prefer additive migrations first.
- Preserve original raw queries.
- Preserve raw evidence snapshot paths when already captured.
- Never mutate historical rows in place when provenance would be lost.
