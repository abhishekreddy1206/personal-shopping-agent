from __future__ import annotations

import re
import socket
import urllib.parse
import urllib.request
from pathlib import Path

from app.models.types import EvidenceSnapshot, OfferCandidate, ParsedIntent
from app.sources.search_utils import analyze_listing_text, parse_price, prepare_search_lines


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
PRICE_RE = re.compile(r"\$(\d+(?:,\d{3})*(?:\.\d{2})?)")


class LiveFetchClient:
    def __init__(self, raw_dir: str | Path, timeout_seconds: int = 8) -> None:
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds

    def fetch_text(self, url: str) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, socket.timeout, TimeoutError):
            return ""

    def save_snapshot(self, source_name: str, query: str, content: str) -> str:
        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", query.strip().lower())[:60] or "query"
        path = self.raw_dir / f"{source_name}-{safe_name}.txt"
        path.write_text(content, encoding="utf-8")
        return str(path)


class LiveAmazonSearchAdapter:
    name = "amazon_live"
    category = "electronics"

    def __init__(self, client: LiveFetchClient) -> None:
        self.client = client

    def search(self, intent: ParsedIntent) -> list[OfferCandidate]:
        search_text = intent.filters.get("product_text") or intent.raw_query
        query = urllib.parse.quote_plus(search_text)
        url = "https://www.amazon.com/s?k=" + query
        text = self.client.fetch_text(url)
        if not text:
            return []
        snapshot = self.client.save_snapshot(self.name, search_text, text)
        title, price = extract_amazon_candidate(text, search_text)
        if title is None:
            return []
        return [
            OfferCandidate(
                source_name=self.name,
                retailer="Amazon",
                listing_url=url,
                title=title,
                base_price=price,
                shipping_price=0.0,
                effective_price=price,
                condition="unknown",
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


class LiveNikeSearchAdapter:
    name = "nike_live"
    category = "clothes_shoes"

    def __init__(self, client: LiveFetchClient) -> None:
        self.client = client

    def search(self, intent: ParsedIntent) -> list[OfferCandidate]:
        search_text = intent.filters.get("product_text") or intent.raw_query
        query = urllib.parse.quote(search_text)
        url = "https://www.nike.com/w?q=" + query
        text = self.client.fetch_text(url)
        if not text:
            return []
        snapshot = self.client.save_snapshot(self.name, search_text, text)
        results = extract_nike_candidates(text)
        offers: list[OfferCandidate] = []
        for title, price in results[:3]:
            offers.append(
                OfferCandidate(
                    source_name=self.name,
                    retailer="Nike",
                    listing_url=url,
                    title=title,
                    base_price=price,
                    shipping_price=0.0,
                    effective_price=price,
                    condition="new",
                    availability="unknown",
                    metadata={
                        "snapshot_path": snapshot,
                        "confidence": "medium",
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
                    verification_state="partially_verified",
                    extraction_confidence="medium",
                )
            )
        return offers


def extract_amazon_candidate(text: str, fallback_query: str) -> tuple[str | None, float | None]:
    intent = ParsedIntent(
        intent_type="search",
        raw_query=fallback_query,
        filters={"product_text": fallback_query},
    )
    lines = prepare_search_lines(text)
    best: tuple[str | None, float | None, float] = (None, None, 0.0)
    for idx, line in enumerate(lines):
        if len(line) < 18:
            continue
        analysis = analyze_listing_text(line, intent)
        if analysis["is_generic"] or analysis["is_accessory"]:
            continue
        price = None
        for follow in lines[idx: idx + 4]:
            price_match = PRICE_RE.search(follow)
            if price_match:
                price = parse_price(price_match.group(1))
                break
        score = float(analysis["score"])
        if price is None or score < 0.9:
            continue
        if score > best[2]:
            best = (line[:240], price, score)
    return best[0], best[1]


def extract_nike_candidates(text: str) -> list[tuple[str, float | None]]:
    lines = prepare_search_lines(text)
    joined = " ".join(lines)
    pattern = re.compile(r"(Nike [A-Za-z0-9\-\+ ]{2,80}?)(?:Men's|Women's|Trail|Road|Waterproof|Racing|Shoes).*?\$(\d+(?:\.\d{2})?)")
    matches = pattern.findall(joined)
    results: list[tuple[str, float | None]] = []
    seen = set()
    for title, price in matches:
        normalized = " ".join(title.split())
        if normalized in seen:
            continue
        seen.add(normalized)
        results.append((normalized, parse_price(price)))
    return results

