from __future__ import annotations

import re

from app.models.types import ClarificationRequest, ParsedIntent, ProductIntent, StructuredIntake, UserQuery, WatchRule


PRICE_PATTERN = re.compile(r"(?:below|under)\s*\$?(\d+(?:\.\d+)?)", re.IGNORECASE)
MODEL_PATTERN = re.compile(r"\b([A-Z]{1,5}(?:-[A-Z0-9]+)+|[A-Z]{1,5}[A-Z0-9]{2,})\b")
SERIES_PATTERN = re.compile(r"\b([A-Z]{1,4}\s?-?\s?\d{2,4})\b", re.IGNORECASE)

BRAND_ALIASES = {
    "senheisser": "sennheiser",
    "sennheiser": "sennheiser",
    "bose": "bose",
    "sony": "sony",
    "nike": "nike",
    "adidas": "adidas",
    "apple": "apple",
    "samsung": "samsung",
}

CONVERSATIONAL_PREFIXES = [
    "find me the best deals for ",
    "find me the best deals on ",
    "find me the best deal for ",
    "find me the best deal on ",
    "find me a good deal on ",
    "find me good deals on ",
    "find me ",
    "show me the best deals for ",
    "show me the best deal on ",
    "show me a good deal on ",
    "best deals for ",
    "best deals on ",
    "best deal for ",
    "best deal on ",
    "track this ",
    "track ",
    "search in marketplace mode for ",
    "hunt aggressively for deals on ",
    "best ",
]

CONVERSATIONAL_FILLER_PATTERNS = [
    r"\ba\s+good\s+deal\s+on\b",
    r"\bgood\s+deals?\s+on\b",
    r"\bthe\s+best\s+deals?\s+for\b",
    r"\bbest\s+deals?\s+for\b",
    r"\bdeals?\s+for\b",
]

ELECTRONICS_TERMS = {
    "monitor", "laptop", "headphones", "headphone", "tv", "phone", "earbuds", "earbud",
    "speaker", "speakers", "dac", "amp", "amplifier", "receiver",
    "sennheiser", "senheisser", "sony", "bose", "samsung", "hd 650", "hd650", "wh-1000xm6",
}

BOSE_QC_ULTRA_PATTERN = re.compile(r"\bbose\s+quiet\s*comfort\s+ultra\s+2\b|\bbose\s+quietcomfort\s+ultra\s+2\b", re.IGNORECASE)
FRAME_TV_PATTERN = re.compile(r"\bsamsung\b.*\bthe\s+frame(?:\s+tv)?\b|\bthe\s+frame\s+tv\b", re.IGNORECASE)
SIZE_ONLY_PATTERN = re.compile(r"\b(\d{2,3})\s*(?:inch|inches|\")\b", re.IGNORECASE)


class IntentParser:
    """Lightweight parser for shopping intents."""

    def parse(self, raw_query: str) -> ParsedIntent:
        return self.parse_structured(raw_query).parsed_intent

    def parse_structured(self, raw_query: str) -> StructuredIntake:
        lowered = raw_query.lower().strip()

        if "watchlist" in lowered:
            intent_type = "watchlist_view"
        elif "history" in lowered or "recent searches" in lowered:
            intent_type = "history_lookup"
        elif "dropped" in lowered:
            intent_type = "drop_summary"
        elif "buy now" in lowered or "wait" in lowered:
            intent_type = "buy_or_wait"
        elif lowered.startswith("watch ") or lowered.startswith("track ") or " track " in f" {lowered} " or " watch " in f" {lowered} ":
            intent_type = "watch_create"
        else:
            intent_type = "search"

        normalized_lowered = self._normalize_query_text(lowered)

        category = None
        category_confidence = 0.3
        if any(term in normalized_lowered for term in ELECTRONICS_TERMS):
            category = "electronics"
            category_confidence = 0.8
        elif any(term in normalized_lowered for term in ["shoe", "shoes", "sneaker", "shirt", "jacket", "hoodie", "running"]):
            category = "clothes_shoes"
            category_confidence = 0.75

        query_shape = "search"
        if intent_type == "watch_create":
            query_shape = "watch_rule"
        elif "best deal" in lowered or "deal" in lowered or "hunt" in lowered:
            query_shape = "deal_hunt"
        elif category and any(term in lowered for term in ["best", "under", "top"]):
            query_shape = "category_search"
        elif category:
            query_shape = "exact_product"

        condition_preference = "any"
        if "used" in lowered:
            condition_preference = "used"
        elif "refurb" in lowered:
            condition_preference = "refurbished"
        elif "new" in lowered:
            condition_preference = "new"

        urgency = "normal"
        if "not urgent" in lowered:
            urgency = "low"
        elif "urgent" in lowered or "asap" in lowered:
            urgency = "urgent"

        target_price = None
        budget_max = None
        match = PRICE_PATTERN.search(raw_query)
        if match:
            value = float(match.group(1))
            if intent_type == "watch_create":
                target_price = value
            else:
                budget_max = value

        filters = {}
        if "marketplace mode" in lowered or "used" in lowered or "ebay" in lowered or "marketplace" in lowered:
            filters["source_mode"] = "trusted_plus_marketplace"
        elif "aggressive" in lowered or "hunt" in lowered or "slickdeals" in lowered or "coupon" in lowered:
            filters["source_mode"] = "aggressive_deal_hunt"
        elif "trusted only" in lowered:
            filters["source_mode"] = "trusted_only"
        else:
            filters["source_mode"] = "trusted_plus_discovery"

        if urgency == "low":
            filters["notes"] = "not urgent"
            filters["check_frequency"] = "weekly"
        elif category == "electronics":
            filters["check_frequency"] = "daily"
        elif category == "clothes_shoes":
            filters["check_frequency"] = "every_2_days"

        product_terms = raw_query.split()
        normalized_query = self._normalize_query_text(raw_query)
        product_text = self._extract_product_text(normalized_query)
        brand = self._extract_brand(normalized_query.lower())
        product_family = self._extract_product_family(normalized_query.lower())
        model_number = self._extract_model_number(normalized_query)
        size = self._extract_size(raw_query)
        filters["product_text"] = product_text
        if brand:
            filters["brand"] = brand
        if product_family:
            filters["product_family"] = product_family
        if model_number:
            filters["model_number"] = model_number
        if size:
            filters["size"] = size

        clarification = self._detect_clarification_need(raw_query, normalized_query, brand, product_family, size)

        parsed_intent = ParsedIntent(
            intent_type=intent_type,
            raw_query=raw_query,
            category=category,
            category_confidence=category_confidence,
            query_shape=query_shape,
            condition_preference=condition_preference,
            urgency=urgency,
            product_terms=product_terms,
            budget_max=budget_max,
            target_price=target_price,
            filters=filters,
            needs_clarification=clarification is not None,
            clarification=clarification,
        )

        product_intent = ProductIntent(
            freeform_product_text=product_text,
            brand=brand,
            product_family=product_family,
            model_number=model_number,
            size=size,
            category=category,
            attributes={"condition_preference": condition_preference},
            canonicalization_status="raw",
            canonicalization_confidence=0.4 if product_text else 0.2,
        )

        user_query = UserQuery(
            raw_text=raw_query,
            request_type=intent_type,
            source_mode_requested=filters["source_mode"],
            parse_status="parsed",
            parser_version="v2",
        )

        watch_rule = None
        if intent_type == "watch_create":
            normalized_subject = self._normalize_watch_subject(product_text, product_family, brand)
            watch_rule = WatchRule(
                normalized_subject=normalized_subject,
                user_label=self._build_watch_label(brand, product_family, product_text),
                target_price=target_price,
                condition_required=condition_preference,
                source_mode=filters["source_mode"],
                preferred_sources=filters.get("preferred_sources", []),
                check_frequency=filters.get("check_frequency", "daily"),
                priority=urgency,
                notes=filters.get("notes"),
            )

        return StructuredIntake(
            user_query=user_query,
            parsed_intent=parsed_intent,
            product_intent=product_intent,
            watch_rule=watch_rule,
            pending_clarification=clarification,
        )

    def _extract_product_text(self, raw_query: str) -> str:
        lowered = raw_query.lower()
        text = raw_query.strip()
        lower_text = lowered
        for prefix in CONVERSATIONAL_PREFIXES:
            if lower_text.startswith(prefix):
                text = text[len(prefix):]
                break
        text = re.sub(r"\b(?:used|refurb(?:ished)?|open\s*box|marketplace|slickdeals|coupon|ebay)\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\bin\s+marketplace\s+mode\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\bin\s+mode\b", "", text, flags=re.IGNORECASE)
        for pattern in CONVERSATIONAL_FILLER_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        text = re.sub(r"if it drops below\s*\$?\d+(?:\.\d+)?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"under\s*\$?\d+(?:\.\d+)?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\b\d+\s*(?:inch|inches|\")\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(?:class)\b", "", text, flags=re.IGNORECASE)
        text = " ".join(text.split())
        return self._humanize_product_text(text or raw_query)

    def _extract_brand(self, lowered: str) -> str | None:
        for alias, canonical in BRAND_ALIASES.items():
            if alias in lowered:
                return canonical.title()
        return None

    def _extract_product_family(self, lowered: str) -> str | None:
        families = {
            "the frame tv": "the frame tv",
            "the frame": "the frame tv",
            "frame tv": "the frame tv",
            "quietcomfort ultra": "headphones",
            "quiet comfort ultra": "headphones",
            "qc ultra": "headphones",
            "hd 650": "headphones",
            "hd650": "headphones",
            "headphones": "headphones",
            "headphone": "headphones",
            "earbuds": "earbuds",
            "monitor": "monitor",
            "running shoes": "running shoes",
            "laptop": "laptop",
            "tv": "tv",
        }
        for key, value in families.items():
            if key in lowered:
                return value
        return None

    def _extract_model_number(self, raw_query: str) -> str | None:
        match = MODEL_PATTERN.search(raw_query)
        if match:
            return match.group(1)
        series_match = SERIES_PATTERN.search(raw_query)
        if series_match:
            return re.sub(r"\s+", " ", series_match.group(1)).strip().upper()
        return None

    def _normalize_query_text(self, text: str) -> str:
        normalized = text
        for alias, canonical in BRAND_ALIASES.items():
            normalized = re.sub(rf"\b{re.escape(alias)}\b", canonical, normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\bhd\s*-?\s*(650)\b", r"HD \1", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\bquiet\s+comfort\b", "QuietComfort", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\bquietcomfort\s+ultra\s+2\b", "QuietComfort Ultra 2", normalized, flags=re.IGNORECASE)
        return normalized

    def _extract_size(self, raw_query: str) -> str | None:
        match = SIZE_ONLY_PATTERN.search(raw_query)
        return f'{match.group(1)} inch' if match else None

    def _detect_clarification_need(
        self,
        raw_query: str,
        normalized_query: str,
        brand: str | None,
        product_family: str | None,
        size: str | None,
    ) -> ClarificationRequest | None:
        lowered = normalized_query.lower()
        if BOSE_QC_ULTRA_PATTERN.search(raw_query) and not any(term in lowered for term in ["headphones", "over-ear", "earbuds", "earbud"]):
            return ClarificationRequest(
                kind="product_type",
                question="Do you mean the Bose QuietComfort Ultra over-ear headphones or the earbuds?",
                options=["over-ear headphones", "earbuds"],
                product_hint="Bose QuietComfort Ultra 2",
                expected_attribute="product_family",
                context={"brand": brand or "Bose", "query": raw_query},
            )
        if FRAME_TV_PATTERN.search(raw_query) and size is None:
            return ClarificationRequest(
                kind="size",
                question="What size Samsung The Frame TV do you want?",
                options=["43 inch", "50 inch", "55 inch", "65 inch"],
                product_hint="Samsung The Frame TV",
                expected_attribute="size",
                context={"brand": brand or "Samsung", "product_family": product_family or "the frame tv", "query": raw_query},
            )
        return None

    def _normalize_watch_subject(self, product_text: str, product_family: str | None, brand: str | None) -> str:
        pieces = []
        if brand:
            pieces.append(brand.lower())
        model_number = self._extract_model_number(product_text)
        if model_number:
            pieces.append(model_number.lower())
        if product_family:
            pieces.append(product_family.lower())
        elif product_text and not model_number:
            pieces.append(product_text.lower())
        return " ".join(pieces).strip() or product_text.lower()

    def _build_watch_label(self, brand: str | None, product_family: str | None, product_text: str) -> str:
        pieces = []
        if product_text:
            return self._humanize_product_text(product_text)
        if brand:
            pieces.append(brand)
        if product_family:
            pieces.append(product_family.title())
        return " ".join(pieces).strip() or product_text

    def _humanize_product_text(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip(" -\t\r\n")
        if not cleaned:
            return text

        model_number = self._extract_model_number(cleaned)
        brand = self._extract_brand(cleaned.lower())
        family = self._extract_product_family(cleaned.lower())
        pieces: list[str] = []
        if brand:
            pieces.append(brand)
        if model_number:
            pieces.append(model_number)
        if family and family.lower() not in cleaned.lower() and not (model_number is None and brand and family.lower() in {"headphones", "earbuds"}):
            pieces.append(family.title())
        if pieces:
            remaining = cleaned
            for piece in pieces:
                remaining = re.sub(rf"\b{re.escape(piece)}\b", "", remaining, flags=re.IGNORECASE)
            remaining = " ".join(remaining.split())
            extra_parts = []
            if remaining:
                extra_parts.append(self._titleize_remaining_text(remaining))
            normalized_joined = " ".join(dict.fromkeys(piece for piece in [*pieces, *extra_parts] if piece))
            normalized_joined = re.sub(r"\bQuietcomfort\b", "QuietComfort", normalized_joined)
            return normalized_joined

        def smart_cap(match: re.Match[str]) -> str:
            token = match.group(0)
            return token if any(char.isdigit() for char in token) else token.capitalize()

        normalized = re.sub(r"[A-Za-z0-9-]+", smart_cap, cleaned)
        return re.sub(r"\bQuietcomfort\b", "QuietComfort", normalized)

    def _titleize_remaining_text(self, text: str) -> str:
        normalized = text.title()
        normalized = re.sub(r"\bQuietcomfort\b", "QuietComfort", normalized)
        return normalized
