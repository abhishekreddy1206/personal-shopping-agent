# Parser, Alert, and Learning Redesign

## Parser redesign

### Deterministic responsibilities
The parser should deterministically extract:
- intent type
- source mode request
- query shape
- category guess + confidence
- budget min/max
- watch target price
- condition preference
- urgency
- product subject text

### Agentic-allowed responsibilities
Use agentic interpretation only for:
- ambiguous product clarification
- query rewriting for better search coverage
- canonical product inference when deterministic rules are insufficient

### Parser output contract
Parser should produce:
- `UserQuery`
- `ParsedIntent`
- `ProductIntent`

## Alert redesign

### Deterministic alert gating
Alerts should be determined by rules, not vibes.

Before an alert is deliverable, require:
- confidence threshold
- dedupe key check
- watch-rule match
- lane eligibility
- source-role eligibility

### Alert decision outcomes
Each potential alert should be stored as:
- send
- suppress

With reasons such as:
- `below_target_price`
- `new_local_low`
- `duplicate_state`
- `low_confidence`
- `marketplace_requires_opt_in`

### Alert delivery boundary
Message wording can be agentic.
Alert eligibility must be deterministic.

## Learning redesign

### Allowed learning inputs
- explicit user feedback
- observed alert usefulness
- repeated source mismatches
- retailer preference signals
- wait-vs-buy outcomes

### Disallowed learning behavior
- self-modifying code
- autonomous trust-tier changes without bounded rules
- direct mutation of deterministic routing logic by freeform model output

### Learning output contract
Learning should update only:
- source-health metrics
- weighted preferences
- category heuristics
- alert usefulness scores

These should be stored in `LearnedPreference` or adjacent structured tables.
