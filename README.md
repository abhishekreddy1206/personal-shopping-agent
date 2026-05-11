# Personal Shopping Agent

A personal Telegram-native shopping agent for search, deal comparison, watchlists, price-drop alerts, and self-improving shopping intelligence.

## Status
Scaffolded project with a local runner, integration runner, service hook, docs, config skeleton, SQLite schema, trusted/live adapter stubs, confidence-aware outputs, and persistence-backed basic flows.

## New architecture work
The project now includes redesign docs for:
- structured schema modeling
- migration planning
- parser/alert/learning boundaries
- deterministic vs agentic separation
- security- and trust-aware flow design

## Project structure
- `app/` application code
- `integrations/` integration contracts and trigger rules
- `config/` source/category/ranking/alert configuration
- `data/` SQLite DB, raw captures, snapshots, exports
- `docs/` engineering docs and redesign specs
- `tests/` test suite

## Key redesign docs
- `docs/schema-redesign.md`
- `docs/migration-plan.md`
- `docs/parser-alert-learning-redesign.md`
- `docs/implementation-priorities.md`
- `docs/flow-audit.md` — record of the issues that caused end-to-end to keep getting stuck across Babji-integrated turns, and the fixes applied. Read this first if you're investigating a "the agent didn't return anything" report.

## Running locally
- Full pytest suite: `python -m pytest tests/ -v`
- Quick deterministic smoke check (no network): `python scripts/smoke_check.py`
- One-shot CLI run: `python -m app.main "Find me the best deal on Sony WH-1000XM6"`
- Telegram entry point (used by Babji): `app.shopping_service.handle_message(text, conversation_key=<chat_id>)`

## Current implementation notes
- OpenClaw/Babji remains Telegram ingress/egress.
- This project remains local-only and domain-focused.
- The current code is still transitional relative to the redesigned schema.
- Future implementation should follow the deterministic-core, agentic-edges model.
- Multi-source live search now includes trusted retail lanes (Amazon, Best Buy, Walmart, Target, Newegg, B&H, Nike), optional discovery signals (Slickdeals), and optional marketplace lanes (eBay) with explicit separation in ranking and output formatting.
- The agent surfaces **only real, web-sourced prices**. Fabricated placeholder/demo offers have been removed; when every live adapter returns nothing, the user sees zero results plus per-adapter telemetry (`payload["adapter_telemetry"]`) showing which lanes ran and what they returned. Enrichment hooks remain honest placeholders until real integrations are connected.

## Near-term roadmap
1. Implement structured intake entities
2. Normalize watch rules and labels
3. Implement evidence and recommendation tables
4. Add alert decision modeling
5. Add bounded learning signals
6. Then expand discovery/marketplace sources more aggressively
