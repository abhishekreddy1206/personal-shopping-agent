from __future__ import annotations

import re
import urllib.parse

from app.models.types import EvidenceSnapshot, OfferCandidate, ParsedIntent
from app.sources.live_fetch import LiveFetchClient
from app.sources.search_utils import (
    analyze_listing_text,
    choose_best_lines,
    extract_structured_offers,
    parse_price,
    prepare_search_lines,
)


class GenericRetailLiveAdapter:
    def __init__(
        self,
        *,
        name: str,
        retailer: str,
        category: str,
        search_url_template: str,
        client: LiveFetchClient,
        source_role: str = "truth",
        lane: str = "trusted_retail",
        verification_state: str = "unverified",
        extraction_confidence: str = "low",
        condition: str = "new",
        require_price: bool = False,
        allow_fallback_stub: bool = False,
    ) -> None:
        self.name = name
        self.retailer = retailer
        self.category = category
        self.search_url_template = search_url_template
        self.client = client
        self.source_role = source_role
        self.lane = lane
        self.verification_state = verification_state
        self.extraction_confidence = extraction_confidence
        self.condition = condition
        self.require_price = require_price
        self.allow_fallback_stub = allow_fallback_stub

    def search(self, intent: ParsedIntent) -> list[OfferCandidate]:
        search_text = intent.filters.get("product_text") or intent.raw_query
        query = urllib.parse.quote_plus(search_text)
        url = self.search_url_template.format(query=query)
        text = self.client.fetch_text(url)
        if not text:
            return []
        snapshot = self.client.save_snapshot(self.name, search_text, text)

        # Try structured-data (JSON-LD / Open Graph) first — modern retailer pages
        # publish product info there explicitly for crawlers, and it survives JS-shell
        # HTML where line scanning fails.
        candidates = self._candidates_from_structured_data(text, intent)
        if not candidates:
            candidates = choose_best_lines(text, intent)
            if self.category == "electronics":
                candidates = self._fill_missing_prices_from_context(text, candidates)
        offers: list[OfferCandidate] = []
        for title, price, score, analysis in candidates:
            if score < 0.34 and price is None:
                continue
            if self.require_price and price is None:
                continue
            if self.category == "electronics" and not self._is_plausible_electronics_price(intent, title, price):
                continue
            normalized_title = self._normalize_title(title, intent, analysis)
            offers.append(
                OfferCandidate(
                    source_name=self.name,
                    retailer=self.retailer,
                    listing_url=url,
                    title=normalized_title,
                    base_price=price,
                    shipping_price=0.0,
                    effective_price=price,
                    condition=self.condition,
                    availability="unknown",
                    metadata={
                        "snapshot_path": snapshot,
                        "confidence": "medium" if score >= 0.72 else "low",
                        "match_score": round(score, 3),
                        "exact_model_match": bool(analysis.get("exact_model_match")),
                        "generic_result": bool(analysis.get("is_generic")),
                        "price_known": price is not None,
                        "source_mode": "live_extract",
                        "lane": self.lane,
                        "trust_tier": "high" if self.source_role == "truth" else "medium",
                    },
                    evidence_snapshot=EvidenceSnapshot(
                        source_name=self.name,
                        storage_path=snapshot,
                        capture_method="live_fetch",
                        sanitized=True,
                        retention_policy="local_debug",
                    ),
                    source_role=self.source_role,
                    verification_state=self.verification_state,
                    extraction_confidence="medium" if score >= 0.72 else self.extraction_confidence,
                )
            )
        return offers

    def _candidates_from_structured_data(
        self,
        text: str,
        intent: ParsedIntent,
    ) -> list[tuple[str, float | None, float, dict[str, object]]]:
        """Convert JSON-LD / Open Graph results into the same shape `choose_best_lines` returns."""
        structured = extract_structured_offers(text)
        if not structured:
            return []
        candidates: list[tuple[str, float | None, float, dict[str, object]]] = []
        for entry in structured:
            title = entry.get("title")
            price = entry.get("price")
            if not title:
                continue
            analysis = analyze_listing_text(title, intent)
            if analysis.get("is_accessory") or analysis.get("is_generic"):
                continue
            score = float(analysis.get("score", 0.0))
            # Structured-data hits are inherently more trustworthy than line scraping;
            # give them a small boost so they aren't discarded by the score floor.
            score += 0.15
            if entry.get("source") == "json_ld":
                score += 0.1
            if score < 0.25 and price is None:
                continue
            candidates.append((title[:240], price, score, dict(analysis)))
        candidates.sort(
            key=lambda item: (
                -int(bool(item[3].get("exact_model_match"))),
                int(item[1] is None),
                -item[2],
                item[1] if item[1] is not None else 10**9,
                item[0],
            )
        )
        return candidates[:4]

    def _fill_missing_prices_from_context(self, text: str, candidates: list[tuple[str, float | None, float, dict[str, object]]]) -> list[tuple[str, float | None, float, dict[str, object]]]:
        if not candidates:
            return candidates
        lines = prepare_search_lines(text)
        priced: list[tuple[str, float | None, float, dict[str, object]]] = []
        for title, price, score, analysis in candidates:
            if price is not None:
                priced.append((title, price, score, analysis))
                continue
            inferred_price = self._infer_price_for_title(lines, title)
            priced.append((title, inferred_price, score, analysis))
        return priced

    def _infer_price_for_title(self, lines: list[str], title: str) -> float | None:
        for idx, line in enumerate(lines):
            if title not in line:
                continue
            window = lines[max(0, idx - 3): min(len(lines), idx + 6)]
            for neighbor in window:
                if title == neighbor:
                    continue
                price = self._extract_price_from_line(neighbor)
                if price is not None:
                    return price
        return None

    def _extract_price_from_line(self, line: str) -> float | None:
        lowered = line.lower()
        if any(term in lowered for term in ["save:", "you save", "discount", "off "]):
            return None
        for match in reversed(list(re.finditer(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', line))):
            price = parse_price(match.group(1))
            if price is not None and price >= 50:
                return price
        return None

    def _is_plausible_electronics_price(self, intent: ParsedIntent, title: str, price: float | None) -> bool:
        if price is None:
            return not self.require_price
        normalized_title = title.lower()
        product_family = ((intent.filters or {}).get("product_family") or "").lower()
        model_number = ((intent.filters or {}).get("model_number") or "").lower()
        if product_family in {"headphones", "earbuds"} or model_number.startswith("hd ") or model_number.startswith("wh-"):
            return price >= 80
        if product_family in {"tv", "the frame tv", "monitor", "laptop"}:
            return price >= 150
        if any(term in normalized_title for term in ["tv", "monitor", "laptop"]):
            return price >= 150
        if any(term in normalized_title for term in ["headphone", "headphones", "earbud", "earbuds"]):
            return price >= 80
        return price >= 25

    def _normalize_title(self, title: str, intent: ParsedIntent, analysis: dict[str, object]) -> str:
        compact = " ".join(title.split())
        if len(compact.split()) >= 3:
            return compact
        if not analysis.get("exact_model_match"):
            return compact
        brand = (intent.filters.get("brand") if intent.filters else None) or ""
        family = (intent.filters.get("product_family") if intent.filters else None) or ""
        model = (intent.filters.get("model_number") if intent.filters else None) or ""
        pieces = [brand, model, family.title() if family else ""]
        expanded = " ".join(piece for piece in pieces if piece).strip()
        return expanded or compact
