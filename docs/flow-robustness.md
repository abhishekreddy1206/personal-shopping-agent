# Flow Robustness Rules

## Core principle
It is better to return fewer trustworthy results than more unreliable ones.

## Robust flow contract
1. Parse the request.
2. Resolve source mode.
3. Query trusted truth sources first.
4. Query discovery sources only if the mode allows it.
5. Query marketplace sources only if the mode allows it.
6. Keep each lane separate until final presentation.
7. Rank within lanes before cross-lane summarization.
8. Expose confidence and evidence metadata.
9. Fall back cleanly on timeouts or extraction failures.

## Failure handling
- One source failure must not fail the entire search.
- One hanging source must time out quickly.
- Low-confidence extraction should be labeled or suppressed.
- Marketplace results should never silently replace trusted-retail results.

## Output contract
Each result should expose:
- retailer
- effective price
- confidence
- source_mode
- has_snapshot
- lane (`trusted_retail`, `discovery_context`, `marketplace`, `enrichment_context`)

## Alert contract
Alerts should only fire when:
- a threshold is crossed
- a meaningful improvement occurs
- the confidence is sufficient for the alert type

Low-confidence discovery signals may produce notes, but should not produce strong alerts by default.
