"""Local smoke check that exercises the major code paths without making real network calls.

Run from repo root:  python scripts/smoke_check.py

This is not a replacement for the pytest suite — it's a quick sanity check that all the
key modules import cleanly and the deterministic parts of the flow behave correctly.
Useful when debugging Babji integration issues where you want to confirm "the project
itself works" before chasing transport problems.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.parser.intent_parser import IntentParser
    from app.sources.search_utils import (
        analyze_listing_text,
        choose_best_lines,
        extract_structured_offers,
        suppress_stub_offers,
    )
    from app.models.types import EvidenceSnapshot, OfferCandidate, ParsedIntent

    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        status = "OK " if ok else "FAIL"
        print(f"[{status}] {name}{(' — ' + detail) if detail else ''}")
        if not ok:
            failures.append(name)

    # 1. Parser
    parser = IntentParser()
    intake = parser.parse_structured("Find me the best deal on Sony WH-1000XM6")
    check("parser: extracts brand+model", intake.parsed_intent.filters.get("brand") == "Sony" and intake.parsed_intent.filters.get("model_number") == "WH-1000XM6")

    intake_clarify = parser.parse_structured("Find me a good deal on Bose QuietComfort Ultra 2")
    check("parser: requests clarification on Bose QC Ultra 2", intake_clarify.parsed_intent.needs_clarification is True)

    # 2. Structured-data extractor
    sample_jsonld = """
    <html><head>
    <script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "Product",
     "name": "Sony WH-1000XM6 Wireless Noise Canceling Headphones",
     "offers": {"@type": "Offer", "price": "399.99"}}
    </script>
    </head></html>
    """
    structured = extract_structured_offers(sample_jsonld)
    check("structured-data: extracts JSON-LD product", len(structured) == 1 and structured[0]["price"] == 399.99)

    sample_og = """
    <html><head>
    <meta property="og:title" content="Nike Pegasus 41">
    <meta property="product:price:amount" content="139.99">
    </head></html>
    """
    structured_og = extract_structured_offers(sample_og)
    check("structured-data: falls back to og:meta", len(structured_og) == 1 and structured_og[0]["price"] == 139.99)

    # 3. Stub-suppression policy: stubs are dropped unconditionally. Only real,
    # web-sourced prices reach the user. "No results" beats a fabricated placeholder.
    only_stub = OfferCandidate(
        source_name="amazon", retailer="Amazon",
        listing_url="https://example.com/x", title="Sony WH-1000XM6 stub",
        effective_price=299.98, base_price=299.98, shipping_price=0.0,
        condition="new", availability="in_stock",
        metadata={"source_mode": "fallback_stub", "lane": "trusted_retail"},
        evidence_snapshot=EvidenceSnapshot(source_name="amazon"),
        source_role="truth", verification_state="partially_verified",
    )
    check("suppression: every stub dropped, no fake answers", suppress_stub_offers([only_stub]) == [])

    # 4. End-to-end: when every adapter returns nothing, the user sees zero offers.
    # No fallback stubs sneak through.
    from app.orchestrator.shopping_orchestrator import ShoppingOrchestrator
    from app.storage.db import connect, initialize_schema
    from app.storage.repository import Repository

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "smoke.db"
        conn = connect(db_path)
        initialize_schema(conn, ROOT / "data" / "db" / "schema.sql")
        orchestrator = ShoppingOrchestrator(Repository(conn))

        class DeadAdaptersRegistry:
            last_telemetry: list = []
            def search(self, intent):
                return []
        orchestrator.registry = DeadAdaptersRegistry()

        result = orchestrator.execute_structured(intake)
        check(
            "end-to-end: dead adapters produce zero offers (no placeholder)",
            result.ranked_offers == [],
        )
        conn.close()

    # 5. Persisted clarification round-trip
    from app.telegram.handler import TelegramHandler

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "clar.db")
        h1 = TelegramHandler(db_path=db_path)
        try:
            first = h1.handle_message("Find me a good deal on Bose QuietComfort Ultra 2")
        finally:
            h1.close()
        h2 = TelegramHandler(db_path=db_path)
        try:
            second = h2.handle_message("earbuds")
        finally:
            h2.close()
        check("clarification: persists across handler reconstruction", first.get("needs_clarification") is True and second.get("needs_clarification") is False)

    print()
    if failures:
        print(f"FAIL: {len(failures)} check(s) failed: {failures}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
