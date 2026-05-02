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

## Current implementation notes
- OpenClaw/Babji remains Telegram ingress/egress.
- This project remains local-only and domain-focused.
- The current code is still transitional relative to the redesigned schema.
- Future implementation should follow the deterministic-core, agentic-edges model.
- Multi-source live search now includes trusted retail lanes (Amazon, Best Buy, Walmart, Target, Newegg, B&H, Nike), optional discovery signals (Slickdeals), and optional marketplace lanes (eBay) with explicit separation in ranking and output formatting.
- Stub fallback offers are now suppressed when live offers exist for the same retailer, and enrichment hooks remain honest placeholders until real integrations are connected.

## Near-term roadmap
1. Implement structured intake entities
2. Normalize watch rules and labels
3. Implement evidence and recommendation tables
4. Add alert decision modeling
5. Add bounded learning signals
6. Then expand discovery/marketplace sources more aggressively
