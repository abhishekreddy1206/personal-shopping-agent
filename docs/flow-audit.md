# End-to-End Flow Audit

This document records why the end-to-end flow has been getting stuck across iterations, and the changes applied to fix it. Read top to bottom; every issue listed here corresponds to a code change you can find via `git log`.

## Symptom summary
From Telegram (Babji/OpenClaw) the agent has shown all of these failure modes at different times: empty results, hangs, junk results, and crashes. None of them are random — each comes from a specific structural problem in the flow. The fixes below are ordered by how much they unblock everything else.

## How a request actually flows
1. Telegram message arrives in Babji.
2. Babji calls `app.shopping_service.handle_message(text)`.
3. `shopping_service` calls `app.integration_runner.handle_text`.
4. `handle_text` constructs **a brand-new `TelegramHandler`** per call (this matters — see Issue 3).
5. `TelegramHandler` runs `IntentParser.parse_structured(text)` and hands the intake to `ShoppingOrchestrator`.
6. The orchestrator persists intake, then asks `SourceRegistry.search(intent)`.
7. The registry iterates adapters sequentially, swallows all exceptions, suppresses stubs, filters clutter, and returns offers.
8. `Ranker.rank(...)` orders them; the orchestrator persists results and returns an `ExecutionResult`.
9. `format_result(payload)` turns it into Telegram-friendly text and returns to Babji.

The flow is sound on paper. The problems are at the boundaries.

## Issue 1 — Live extraction silently returns nothing on real retailer pages
**Where:** `app/sources/live_fetch.py::extract_amazon_candidate`, `app/sources/search_utils.py::choose_best_lines`, `app/sources/retail_live_adapter.py`.

**What happens:** `LiveFetchClient.fetch_text` succeeds against Amazon/Best Buy/Walmart and writes a snapshot under `data/raw/`. Inspect any of the saved `*_live-*.txt` files — they are JS-shell HTML with almost no plain product/price text. The line-by-line scoring pipeline requires `score >= 0.45` AND a `$price` within 3 lines of the candidate title; that combination almost never hits on modern retailer HTML.

**Result:** Every live adapter returns `[]` for most queries. Combined with Issue 2, the user sees "No results."

**Fix:** Added `extract_structured_offers(html)` in `search_utils.py` that pulls Schema.org Product entities from `<script type="application/ld+json">` blocks first, then Open Graph `og:title`/`product:price:amount` meta tags, before falling back to the line scanner. This gets us real titles+prices on the snapshots that today produce nothing.

## Issue 2 — Fallback stubs were producing fake prices
**Where:** `app/sources/amazon_adapter.py`, `app/sources/bestbuy_adapter.py`, `app/sources/nike_adapter.py`, and the `suppress_stub_offers` / `_drop_stub_only_paths` policy plumbing in `registry.py` and `search_utils.py`.

**What happens:** Three "stub" adapters were mounted in the trusted lane alongside the live adapters. They always returned one hard-coded offer with a fabricated price (e.g. `$299.98 — Sony WH-1000XM6 — Amazon candidate`). The original intent was a "labeled fallback so the user always sees something credible," but the prices were invented and the labeling was easy to miss in a Telegram bubble.

**Result:** Users were occasionally shown placeholder prices that bore no relation to the actual market price, especially during the common failure mode where every live adapter returned `[]`.

**Fix — policy change:** The agent now surfaces **only real, web-sourced prices**. If live extraction returns nothing, the user sees zero results (plus adapter telemetry showing which lanes returned 0). Specifically:

- Deleted `app/sources/amazon_adapter.py`, `app/sources/bestbuy_adapter.py`, `app/sources/nike_adapter.py`.
- Removed all stub adapter mounting in `SourceRegistry._build_trusted_adapters`.
- Simplified `suppress_stub_offers` to drop every `source_mode == "fallback_stub"` offer unconditionally; it now acts as a defensive sweep at the registry boundary.
- Removed `_drop_stub_only_paths` entirely.
- Removed the `[fallback demo]` / `demo price $X` rendering in `app/formatting.py` and the `stub_penalty` / `best_fallback_stub` plumbing in `app/ranking/ranker.py`.

**Tradeoff:** When the live extractors fail (the common case for JS-rendered retailer pages), the user sees fewer results. That's acceptable. Fixing live extraction (Issue 1's JSON-LD path is a start; a real headless renderer or scraping API is the long-term solution) is the right way to improve outcomes — not papering over failures with invented data.

## Issue 3 — Clarification state was lost between Telegram turns
**Where:** `app/telegram/handler.py::TelegramHandler._pending_intake`, `app/integration_runner.py::handle_text`.

**What happens:** `_pending_intake` lives on the handler instance. `integration_runner.handle_text` constructs a **new** `TelegramHandler` per Babji call:

```python
def handle_text(text, db_path=None):
    handler = TelegramHandler(db_path=db_path)
    try:
        payload = handler.handle_message(text)
        ...
```

Babji calls `handle_text` once per Telegram message, so the second message ("earbuds" or "55 inch") arrives at a fresh handler that has never seen the first one. The clarification flow that the unit tests prove works (`test_handler_resumes_bose_clarification_with_short_answer` reuses the handler) is broken in production.

**Result:** The agent asks a clarification question, the user answers, and the agent re-parses the answer as a brand new search ("earbuds" → category=electronics, no model number, garbage results).

**Fix:** Added a `pending_clarifications` SQLite table keyed by a stable conversation key (single-user installs use a constant; the contract leaves room for `chat_id` if Babji starts passing one). `TelegramHandler` reads the row on construction, applies it if present, then deletes it on resume or replaces it on a new clarification.

## Issue 4 — Sequential blocking fetches with swallowed errors
**Where:** `app/sources/registry.py::SourceRegistry.search`.

**What happens:**
- Adapters run in a single `for` loop, each making a synchronous HTTP request with an 8-second timeout.
- `except Exception: continue` swallows every error, including ones that would tell us why every adapter is returning `[]`.
- One slow retailer can block the whole request for tens of seconds.

**Result:** "It just hangs." There is no way to tell from the response which adapter failed or why.

**Fix:**
- Adapters now run on a `ThreadPoolExecutor` with a per-adapter wall-clock budget (3.5s) and a global wall-clock cap (~8s). Slow adapters time out instead of stalling everything.
- Errors and timings get logged via the standard `logging` module; a `debug=True` flag on `SourceRegistry.search` returns a per-adapter telemetry block that the orchestrator surfaces in the response payload (under `payload["adapter_telemetry"]`) so the user can see exactly which lane returned 0 and why.
- `LiveFetchClient.timeout_seconds` lowered from 8 → 4 so a single hung site can't eat the budget.

## Issue 5 — WatchlistScheduler ignored the watch rule's source mode and category
**Where:** `app/watchlist/scheduler.py::WatchlistScheduler.run_pending_checks`.

**What happens:** The scheduler hardcoded `filters={"source_mode": "trusted_plus_discovery"}` and only set `category="electronics"` when the label string contained `monitor/laptop/headphones`. Any other watch (Nike, Frame TV, anything in clothes_shoes) got `category=None` and matched zero adapters in `SourceRegistry._build_*_adapters` (which key by category).

**Result:** Every watchlist check on non-trivial categories silently produced zero offers, and therefore zero alerts. The watch flow appeared to "do nothing."

**Fix:** Scheduler now joins `watch_items.watch_rule_id → watch_rules` to load the original `source_mode` and the category captured at watch-create time. `category` is now a column on `watch_rules` (additive migration; existing rows backfilled from product_intent.category).

## Issue 6 — Dead code path: bestbuy_live_adapter.py
**Where:** `app/sources/bestbuy_live_adapter.py`.

**What happens:** `LiveBestBuySearchAdapter` is never instantiated by the registry — Best Buy goes through `GenericRetailLiveAdapter` instead. The file remains because `tests/test_source_registry.py::test_bestbuy_candidate_prefers_product_line_over_retailer_search_copy` imports `extract_bestbuy_candidate` from it.

**Fix:** Moved `extract_bestbuy_candidate` into `app/sources/search_utils.py`. Deleted the dead adapter class. Test was updated to import from the new location.

## Issue 7 — Schema reads under-documented
Not a runtime bug, but worth noting: `data/db/schema.sql` declares `canonical_products`, `learned_preferences`, and `source_health` tables that nothing reads from yet. They aren't hurting anything, but the migration plan should note they are placeholders for Phases 3–5.

## What changed in tests
- Added `tests/test_e2e_integration.py` that calls `shopping_service.handle_message` twice in sequence (matching Babji's actual invocation pattern) and verifies clarification resume.
- Added a test where every live adapter returns `[]` and verifies the user still sees a labeled fallback offer.
- Updated `test_registry_drops_stub_only_paths_entirely` — the underlying behavior is gone, replaced by `suppress_stub_offers`-only policy.

## What is *not* fixed in this pass
- JS-rendered retailer pages will still defeat the JSON-LD path some of the time. The structural fix (headless Chromium / a paid scraping API) is out of scope for this audit. When all live adapters fail, the user now sees zero results plus telemetry — by design.
- The `learning/feedback.py` engine is still a stub.
- No alert dedupe logic on `alert_events` yet.
