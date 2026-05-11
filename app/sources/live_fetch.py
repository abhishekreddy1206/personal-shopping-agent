from __future__ import annotations

import gzip
import re
import socket
import urllib.parse
import urllib.request
from pathlib import Path

from app.models.types import EvidenceSnapshot, OfferCandidate, ParsedIntent
from app.sources.search_utils import analyze_listing_text, extract_structured_offers, parse_price, prepare_search_lines


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}
PRICE_RE = re.compile(r"\$(\d+(?:,\d{3})*(?:\.\d{2})?)")


class LiveFetchClient:
    def __init__(self, raw_dir: str | Path, timeout_seconds: int = 4) -> None:
        # Per-fetch timeout lowered from 8s to 4s so a single slow retailer cannot consume
        # the whole search budget. The registry runs adapters concurrently with a global
        # ~8s budget; see app/sources/registry.py.
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds

    def fetch_text(self, url: str) -> str:
        headers = dict(DEFAULT_HEADERS)
        if "ebay.com" in url:
            headers["Referer"] = "https://www.ebay.com/"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
                encoding = response.headers.get("Content-Encoding", "").lower()
                if "gzip" in encoding:
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
                encoding = exc.headers.get("Content-Encoding", "").lower() if exc.headers else ""
                if "gzip" in encoding:
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", errors="replace")
            except Exception:
                return ""
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError):
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
        # Prefer structured-data extraction; modern Amazon pages embed product JSON-LD
        # blocks that survive even when the visible HTML is JS-shell garbage.
        title, price = _structured_first_amazon_candidate(text, intent, search_text)
        if title is None:
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
        # Try structured-data first; Nike's product pages publish full Schema.org Product
        # JSON-LD with offers. Fall back to the regex extractor if nothing's there.
        structured = extract_structured_offers(text)
        results: list[tuple[str, float | None]] = []
        for entry in structured:
            title = entry.get("title")
            if not title:
                continue
            results.append((" ".join(title.split()), entry.get("price")))
        if not results:
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


def _structured_first_amazon_candidate(
    text: str,
    intent: ParsedIntent,
    fallback_query: str,
) -> tuple[str | None, float | None]:
    structured = extract_structured_offers(text)
    if not structured:
        return None, None
    scoring_intent = intent if intent.filters.get("product_text") else ParsedIntent(
        intent_type="search",
        raw_query=fallback_query,
        filters={"product_text": fallback_query},
    )
    best: tuple[str | None, float | None, float] = (None, None, 0.0)
    for entry in structured:
        title = entry.get("title")
        if not title:
            continue
        analysis = analyze_listing_text(title, scoring_intent)
        if analysis.get("is_accessory") or analysis.get("is_generic"):
            continue
        score = float(analysis.get("score", 0.0)) + 0.15
        if entry.get("price") is None and score < 0.7:
            continue
        if score > best[2]:
            best = (title[:240], entry.get("price"), score)
    return best[0], best[1]


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

