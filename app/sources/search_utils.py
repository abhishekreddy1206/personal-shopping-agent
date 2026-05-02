from __future__ import annotations

import html
import re
from typing import Iterable

from app.models.types import OfferCandidate, ParsedIntent

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

    matched_tokens = [token for token in query_tokens if token in normalized_title]
    matched = len(matched_tokens)
    score = matched / float(len(query_tokens))
    missing_tokens = [token for token in query_tokens if token not in normalized_title]
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
        if candidate_price is None and idx + 1 < len(lines):
            neighbor_match = PRICE_RE.search(lines[idx + 1])
            if neighbor_match:
                candidate_price = parse_price(neighbor_match.group(1))
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


def suppress_stub_offers(offers: Iterable[OfferCandidate]) -> list[OfferCandidate]:
    offers = list(offers)
    live_retailers = {
        offer.retailer
        for offer in offers
        if offer.metadata.get("source_mode") == "live_extract"
    }
    has_priced_live_retail = any(
        offer.metadata.get("source_mode") == "live_extract"
        and (offer.metadata.get("lane") or offer.metadata.get("source_family") or "trusted_retail") == "trusted_retail"
        and offer.effective_price is not None
        for offer in offers
    )
    if not live_retailers and not has_priced_live_retail:
        return offers
    filtered: list[OfferCandidate] = []
    for offer in offers:
        is_stub = offer.metadata.get("source_mode") == "fallback_stub"
        if not is_stub:
            filtered.append(offer)
            continue
        if has_priced_live_retail:
            continue
        if offer.retailer in live_retailers:
            continue
        filtered.append(offer)
    return filtered
