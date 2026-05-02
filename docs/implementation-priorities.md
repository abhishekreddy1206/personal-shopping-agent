# Implementation Priorities After Schema Redesign

## Priority 1 — structured intake
Implement:
- `UserQuery`
- `ParsedIntent`
- `ProductIntent`

Reason:
The rest of the system depends on better input structure.

## Priority 2 — watch-rule cleanup
Implement:
- `WatchRule`
- normalized display labels
- target-rule separation from raw text

Reason:
Current watch tracking still mixes display and logic.

## Priority 3 — evidence model
Implement:
- `EvidenceSnapshot`
- `OfferEvidence`
- verification state
- extraction confidence

Reason:
Search quality, trust, and alerting depend on evidence discipline.

## Priority 4 — recommendation and alert decisions
Implement:
- `RankedRecommendation`
- `AlertDecision`

Reason:
This makes display and alerting auditable.

## Priority 5 — learning model
Implement:
- `LearningSignal`
- aligned `LearnedPreference`

Reason:
Improvement should be bounded and structured, not ad hoc.

## Priority 6 — advanced agentic interpretation
After the deterministic spine is stable, add agentic support for:
- better buy-now vs wait summaries
- better query rewriting
- better explanation quality
- better ambiguous-product clarification
