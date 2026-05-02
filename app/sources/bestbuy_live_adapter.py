from __future__ import annotations

import re
import urllib.parse

from app.models.types import EvidenceSnapshot, OfferCandidate, ParsedIntent
from app.sources.live_fetch import LiveFetchClient, parse_price
from app.sources.search_utils import analyze_listing_text, prepare_search_lines


PRICE_RE = re.compile(r"\$(\d+(?:,\d{3})*(?:\.\d{2})?)")


class LiveBestBuySearchAdapter:
    name = "best_buy_live"
    category = "electronics"

    def __init__(self, client: LiveFetchClient) -> None:
        self.client = client

    def search(self, intent: ParsedIntent) -> list[OfferCandidate]:
        query = urllib.parse.quote_plus(intent.raw_query)
        url = "https://www.bestbuy.com/site/searchpage.jsp?st=" + query
        text = self.client.fetch_text(url)
        if not text:
            return []
        snapshot = self.client.save_snapshot(self.name, intent.raw_query, text)
        candidate = extract_bestbuy_candidate(text, intent.raw_query)
        if candidate is None:
            return []
        title, price = candidate
        return [
            OfferCandidate(
                source_name=self.name,
                retailer="Best Buy",
                listing_url=url,
                title=title,
                base_price=price,
                shipping_price=0.0,
                effective_price=price,
                condition="new",
                availability="unknown",
                metadata={
                    "snapshot_path": snapshot,
                    "confidence": "low",
                    "source_mode": "live_extract",
                    "lane": "trusted_retail",
                },
                evidence_snapshot=EvidenceSnapshot(
                    source_name=self.name,
                    storage_path=snapshot,
                    capture_method="live_fetch",
                    sanitized=True,
                    retention_policy="local_debug",
                ),
                source_role="truth",
                verification_state="unverified",
                extraction_confidence="low",
            )
        ]


def extract_bestbuy_candidate(text: str, fallback_query: str) -> tuple[str, float | None] | None:
    lines = prepare_search_lines(text)
    best: tuple[str, float | None, float] | None = None
    for idx, line in enumerate(lines):
        analysis = analyze_listing_text(line, ParsedIntent(intent_type="search", raw_query=fallback_query, filters={}))
        if analysis.get("is_generic") or analysis.get("is_accessory"):
            continue
        price_match = PRICE_RE.search(line)
        candidate_price = parse_price(price_match.group(1)) if price_match else None
        if candidate_price is None and idx + 1 < len(lines):
            neighbor_match = PRICE_RE.search(lines[idx + 1])
            if neighbor_match:
                candidate_price = parse_price(neighbor_match.group(1))
        score = float(analysis.get("score", 0.0)) + (0.15 if candidate_price is not None else 0.0)
        if len(line) <= 8 or score <= 0:
            continue
        candidate = (line[:240], candidate_price, score)
        if best is None or candidate[2] > best[2]:
            best = candidate
    if best is not None:
        return best[0], best[1]
    return None
