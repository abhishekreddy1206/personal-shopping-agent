from __future__ import annotations

import html
import json
import re
from typing import Iterable

from app.models.types import OfferCandidate, ParsedIntent


JSON_LD_BLOCK_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
META_PROPERTY_RE = re.compile(
    r'<meta[^>]*?(?:property|name)=["\']([^"\']+)["\'][^>]*?content=["\']([^"\']*)["\']',
    re.IGNORECASE,
)
META_PROPERTY_REVERSED_RE = re.compile(
    r'<meta[^>]*?content=["\']([^"\']*)["\'][^>]*?(?:property|name)=["\']([^"\']+)["\']',
    re.IGNORECASE,
)

PRICE_RE = re.compile(r"\$(\d+(?:,\d{3})*(?:\.\d{2})?)")
TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
MODEL_RE = re.compile(r"\b[A-Z0-9]{2,}(?:-[A-Z0-9]+)*\b")

ACCESSORY_TERMS = {
    "accessory",
    "accessories",
    "case",
    "cases",
    "pouch",
    "pouches",
    "cover",
    "covers",
    "skin",
    "replacement",
    "replacements",
    "earpad",
    "earpads",
    "pad",
    "pads",
    "cable",
    "cables",
    "charger",
    "chargers",
    "adapter",
    "adapters",
    "part",
    "parts",
    "strap",
    "shell",
    "bundle",
    "bundles",
    "dvd burner",
    "ssd",
    "memory card",
    "usb drive",
    "soundbar",
    "bezel",
}

GENERIC_PAGE_TERMS = {
    "search results",
    "shop",
    "browse",
    "deals",
    "what can we help you find",
    "get fast shipping and top-rated customer service",
    "you will love at great low prices",
    "free shipping on orders",
    "brand store",
    "access denied",
    "you don't have permission",
    "errors.edgesuite.net",
}

UNWANTED_CONDITION_TERMS = {
    "refurb",
    "refurbished",
    "renewed",
    "open box",
    "open-box",
    "pre-owned",
    "preowned",
    "used",
}

MARKETPLACE_TERMS = {
    "marketplace",
    "seller",
    "third party",
    "third-party",
}

GENERIC_RETAILER_PAGE_RE = re.compile(r'^["\']?[a-z0-9\- ]+["\']?\s*[:|]\s*(target|walmart|amazon|best buy|newegg(?:\.com)?|b&h)$')
SEARCH_PAGE_RE = re.compile(r'^(search|shop)\s+(?:[a-z0-9\- ]+?)\s+(?:for|on)\s+', re.IGNORECASE)


KNOWN_NOISE = {
    "find",
    "best",
    "deal",
    "price",
    "track",
    "watch",
    "under",
    "below",
    "monitor",
    "search",
    "mode",
    "trusted",
    "marketplace",
    "aggressive",
    "hunt",
    "coupon",
    "deals",
    "for",
    "this",
    "me",
    "on",
    "if",
    "it",
    "drops",
    "buy",
    "wait",
    "inch",
    "class",
    "tv",
    "in",
}


def parse_price(value: str) -> float | None:
    try:
        return float(value.replace(",", ""))
    except Exception:
        return None


def normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def extract_query_tokens(intent: ParsedIntent) -> list[str]:
    model = intent.filters.get("model_number") if intent.filters else None
    preferred_text = (intent.filters.get("product_text") if intent.filters else None) or intent.raw_query
    raw_tokens = TOKEN_RE.findall(preferred_text)
    tokens: list[str] = []
    for token in raw_tokens:
        lowered = token.lower()
        if len(lowered) < 2 or lowered in KNOWN_NOISE:
            continue
        tokens.append(lowered)
    if model:
        tokens.append(str(model).lower())
    deduped: list[str] = []
    seen = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def extract_model_tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in MODEL_RE.finditer(text)]


def title_match_score(title: str, intent: ParsedIntent) -> float:
    return analyze_listing_text(title, intent)["score"]


def analyze_listing_text(title: str, intent: ParsedIntent) -> dict[str, object]:
    normalized_title = normalize_text(title)
    compact_title = re.sub(r'\s+', ' ', title).strip()
    query_tokens = extract_query_tokens(intent)
    if not query_tokens:
        return {"score": 0.0, "is_accessory": False, "is_generic": False, "exact_model_match": False}

    score = 0.0
    matched_tokens = [token for token in query_tokens if token in normalized_title]
    matched = len(matched_tokens)
    missing_tokens = [token for token in query_tokens if token not in normalized_title]
    if query_tokens:
        score += matched / float(len(query_tokens))
    model_number = intent.filters.get("model_number") if intent.filters else None
    model_token = str(model_number).lower() if model_number else None
    exact_model_match = bool(model_token and model_token in normalized_title)
    if exact_model_match:
        score += 0.4

    title_models = extract_model_tokens(title)
    if model_token and title_models and model_token not in title_models:
        score -= 0.35
    elif model_token and not title_models and model_token not in normalized_title:
        score -= 0.2

    brand = (intent.filters.get("brand") or "").lower() if intent.filters else ""
    if brand and brand in normalized_title:
        score += 0.05

    product_family = (intent.filters.get("product_family") or "").lower() if intent.filters else ""
    family_terms: list[str] = []
    matched_family_terms: list[str] = []
    if product_family and product_family in normalized_title:
        score += 0.2
    elif product_family == "the frame tv":
        family_terms = ["the frame", "frame tv", "art mode"]
        matched_family_terms = [term for term in family_terms if term in normalized_title]
        if matched_family_terms:
            score += 0.25
        else:
            score -= 0.45
        if "tv" not in normalized_title and "class" not in normalized_title:
            score -= 0.55

    size_matches = re.findall(r'(?:\b|\D)(\d{2,3})(?:["”]|\s*inch|\s*inches)', normalized_title)
    requested_size = None
    size_filter = (intent.filters.get("size") if intent.filters else None) or ""
    requested_size_match = re.search(r'(\d{2,3})', str(size_filter)) if size_filter else None
    if requested_size_match:
        requested_size = requested_size_match.group(1)
    if requested_size and size_matches:
        if requested_size in size_matches:
            score += 0.35
        else:
            score -= 0.7

    if product_family == "the frame tv" and not matched_family_terms and "the frame" not in normalized_title:
        score -= 0.45
    if "speaker" in normalized_title or "wireless one connect" in normalized_title:
        score -= 0.35
    if len(size_matches) == 0 and product_family == "the frame tv":
        score -= 0.2
    if len(size_matches) > 1:
        score -= 0.2

    if len(query_tokens) >= 2 and matched < max(2, len(query_tokens) // 2):
        score -= 0.45
    if missing_tokens:
        score -= min(0.35, 0.08 * len(missing_tokens))
    if product_family == "the frame tv" and not family_terms and "tv" not in normalized_title and "class" not in normalized_title:
        score -= 0.6

    is_accessory = any(term in normalized_title for term in ACCESSORY_TERMS)
    if is_accessory:
        score -= 0.75

    lowered_pref = (intent.condition_preference or "any").lower()
    has_unwanted_condition = any(term in normalized_title for term in UNWANTED_CONDITION_TERMS)
    if lowered_pref == "new" and has_unwanted_condition:
        score -= 0.8
    elif lowered_pref == "any" and has_unwanted_condition:
        score -= 0.45

    has_marketplace_language = any(term in normalized_title for term in MARKETPLACE_TERMS)
    if has_marketplace_language and (intent.filters or {}).get("source_mode") != "trusted_plus_marketplace":
        score -= 0.3

    is_generic = any(term in normalized_title for term in GENERIC_PAGE_TERMS)
    if normalized_title.startswith("find me the best deal on") or normalized_title.startswith('"find me the best deal on'):
        is_generic = True
    if GENERIC_RETAILER_PAGE_RE.match(normalized_title):
        is_generic = True
    if SEARCH_PAGE_RE.match(normalized_title):
        is_generic = True
    if compact_title.startswith("<!DOCTYPE") or "<html" in compact_title.lower() or "charSet=" in compact_title:
        is_generic = True
    if is_generic:
        score -= 0.55

    return {
        "score": max(score, 0.0),
        "is_accessory": is_accessory,
        "is_generic": is_generic,
        "exact_model_match": exact_model_match,
        "has_unwanted_condition": has_unwanted_condition,
        "has_marketplace_language": has_marketplace_language,
    }


def choose_best_lines(text: str, intent: ParsedIntent, max_candidates: int = 4) -> list[tuple[str, float | None, float, dict[str, object]]]:
    lines = prepare_search_lines(text)
    candidates: list[tuple[str, float | None, float, dict[str, object]]] = []
    for idx, line in enumerate(lines):
        price_match = PRICE_RE.search(line)
        candidate_title = line
        candidate_price = parse_price(price_match.group(1)) if price_match else None
        if not candidate_title or len(candidate_title) < 8:
            continue
        analysis = analyze_listing_text(candidate_title, intent)
        score = float(analysis["score"])
        if candidate_price is None:
            for neighbor in lines[idx + 1: idx + 4]:
                neighbor_lower = neighbor.lower()
                if any(term in neighbor_lower for term in ["save:", "you save", "discount", "off "]):
                    continue
                neighbor_match = PRICE_RE.search(neighbor)
                if neighbor_match:
                    candidate_price = parse_price(neighbor_match.group(1))
                    break
        if analysis["is_accessory"]:
            continue
        if analysis["is_generic"]:
            continue
        if analysis.get("has_unwanted_condition") and (intent.condition_preference or "any") == "new":
            continue
        if intent.filters.get("model_number") and not analysis["exact_model_match"] and score < 0.85:
            continue
        if score <= 0 and candidate_price is None:
            continue
        if candidate_price is None and float(analysis["score"]) < 0.9:
            continue
        if score < 0.45:
            continue
        candidates.append((candidate_title[:240], candidate_price, score, analysis))
    candidates.sort(
        key=lambda item: (
            -int(bool(item[3].get("exact_model_match"))),
            int(bool(item[3].get("is_generic"))),
            int(item[1] is None),
            -item[2],
            item[1] if item[1] is not None else 10**9,
            item[0],
        )
    )
    deduped: list[tuple[str, float | None, float, dict[str, object]]] = []
    seen = set()
    for item in candidates:
        key = normalize_text(item[0])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= max_candidates:
            break
    return deduped


def prepare_search_lines(text: str) -> list[str]:
    cleaned = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"<style[\s\S]*?</style>", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", "\n", cleaned)
    cleaned = html.unescape(cleaned)
    raw_lines = [line.strip(" -|\t\r\n") for line in cleaned.splitlines()]
    lines: list[str] = []
    seen = set()
    for line in raw_lines:
        normalized = " ".join(line.split())
        lowered = normalized.lower()
        if len(normalized) < 8 and not PRICE_RE.search(normalized):
            continue
        if lowered.startswith(("http", "function", "var ", "window.", "document.")):
            continue
        if normalized.count("<") or normalized.count(">{"):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        lines.append(normalized)
    return lines


def extract_structured_offers(text: str) -> list[dict]:
    """Pull product/offer entries from a retailer page using structured-data markup.

    Modern retailer pages embed product info in `<script type="application/ld+json">`
    blocks (Schema.org Product/Offer) and Open Graph meta tags. This is far more
    reliable than scraping line-by-line because retailers explicitly publish it for
    search engines and crawlers. Returns a list of dicts with keys:
      - title (str | None)
      - price (float | None)
      - url (str | None)
      - source (str — "json_ld" | "og_meta" — for telemetry)

    Empty list if nothing was found. Callers can then fall back to `choose_best_lines`.
    """
    results: list[dict] = []
    seen_titles: set[str] = set()

    for match in JSON_LD_BLOCK_RE.finditer(text):
        block = match.group(1).strip()
        try:
            data = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        for entry in _iter_json_ld_products(data):
            title = _coerce_string(entry.get("name"))
            if not title:
                continue
            normalized = " ".join(title.split())
            if normalized.lower() in seen_titles:
                continue
            seen_titles.add(normalized.lower())
            price = _extract_json_ld_price(entry)
            url = _coerce_string(entry.get("url"))
            results.append({"title": normalized, "price": price, "url": url, "source": "json_ld"})

    if not results:
        meta = _extract_meta_properties(text)
        og_title = meta.get("og:title") or meta.get("twitter:title")
        og_price = (
            meta.get("product:price:amount")
            or meta.get("og:price:amount")
            or meta.get("twitter:data1")
        )
        og_url = meta.get("og:url")
        if og_title:
            normalized = " ".join(og_title.split())
            price_value = parse_price(og_price.replace("$", "").strip()) if og_price else None
            results.append({"title": normalized[:240], "price": price_value, "url": og_url, "source": "og_meta"})

    return results


def _iter_json_ld_products(data):
    """Yield Product-like dicts out of arbitrarily nested JSON-LD payloads."""
    if isinstance(data, list):
        for item in data:
            yield from _iter_json_ld_products(item)
        return
    if not isinstance(data, dict):
        return
    if "@graph" in data:
        for item in data.get("@graph") or []:
            yield from _iter_json_ld_products(item)
    type_value = data.get("@type")
    types = type_value if isinstance(type_value, list) else [type_value]
    if any(t in {"Product", "ProductGroup", "IndividualProduct"} for t in types if isinstance(t, str)):
        yield data
    if any(t == "ItemList" for t in types if isinstance(t, str)):
        for entry in data.get("itemListElement") or []:
            if isinstance(entry, dict):
                yield from _iter_json_ld_products(entry.get("item") or entry)


def _extract_json_ld_price(entry: dict) -> float | None:
    offer = entry.get("offers")
    if isinstance(offer, list):
        prices = [_extract_json_ld_price({"offers": o}) for o in offer]
        prices = [p for p in prices if p is not None]
        return min(prices) if prices else None
    if isinstance(offer, dict):
        for key in ("price", "lowPrice", "highPrice"):
            value = offer.get(key)
            if value is None:
                continue
            try:
                return float(str(value).replace(",", "").replace("$", "").strip())
            except (ValueError, TypeError):
                continue
    return None


def _coerce_string(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list) and value:
        return _coerce_string(value[0])
    if isinstance(value, dict):
        return _coerce_string(value.get("@value") or value.get("name") or value.get("url"))
    return str(value)


def _extract_meta_properties(text: str) -> dict[str, str]:
    properties: dict[str, str] = {}
    for match in META_PROPERTY_RE.finditer(text):
        key = match.group(1).strip().lower()
        value = html.unescape(match.group(2)).strip()
        if key and value and key not in properties:
            properties[key] = value
    for match in META_PROPERTY_REVERSED_RE.finditer(text):
        value = html.unescape(match.group(1)).strip()
        key = match.group(2).strip().lower()
        if key and value and key not in properties:
            properties[key] = value
    return properties


def extract_bestbuy_candidate(text: str, fallback_query: str) -> tuple[str, float | None] | None:
    """Pick the best (title, price) candidate from a Best Buy search snapshot.

    Originally lived in `app/sources/bestbuy_live_adapter.py` (now removed) but the
    live Best Buy adapter is built from `GenericRetailLiveAdapter`. Kept here because
    one regression test still pins this exact behavior, and it's a useful utility.
    """
    lines = prepare_search_lines(text)
    best: tuple[str, float | None, float] | None = None
    scoring_intent = ParsedIntent(intent_type="search", raw_query=fallback_query, filters={})
    for idx, line in enumerate(lines):
        analysis = analyze_listing_text(line, scoring_intent)
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


def suppress_stub_offers(offers: Iterable[OfferCandidate]) -> list[OfferCandidate]:
    """Drop every offer flagged as a fallback stub.

    Policy: the agent surfaces only real, web-sourced prices. If live extraction
    returns nothing, the user sees "no results" plus adapter telemetry — never a
    fabricated placeholder offer. This filter runs at the registry boundary as a
    defensive sweep so any future regression that reintroduces a stub adapter is
    caught before reaching the user.
    """
    return [
        offer for offer in offers
        if offer.metadata.get("source_mode") != "fallback_stub"
    ]
