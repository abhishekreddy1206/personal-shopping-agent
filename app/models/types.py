from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UserQuery:
    raw_text: str
    channel: str = "telegram"
    surface: str = "telegram"
    request_type: str = "search"
    source_mode_requested: str = "trusted_plus_discovery"
    parse_status: str = "parsed"
    parser_version: str = "v2"


@dataclass
class ParsedIntent:
    intent_type: str
    raw_query: str
    category: str | None = None
    category_confidence: float | None = None
    query_shape: str | None = None
    condition_preference: str | None = None
    urgency: str | None = None
    product_terms: list[str] = field(default_factory=list)
    budget_min: float | None = None
    budget_max: float | None = None
    target_price: float | None = None
    filters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProductIntent:
    freeform_product_text: str
    brand: str | None = None
    product_family: str | None = None
    model_number: str | None = None
    variant: str | None = None
    size: str | None = None
    color: str | None = None
    category: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    canonicalization_status: str = "raw"
    canonicalization_confidence: float | None = None


@dataclass
class WatchRule:
    normalized_subject: str
    user_label: str
    target_price: float | None = None
    target_drop_percent: float | None = None
    condition_required: str | None = None
    source_mode: str = "trusted_plus_discovery"
    preferred_sources: list[str] = field(default_factory=list)
    check_frequency: str = "daily"
    priority: str = "normal"
    active: bool = True
    notes: str | None = None


@dataclass
class EvidenceSnapshot:
    source_name: str
    storage_path: str | None = None
    content_type: str = "text/plain"
    capture_method: str = "unknown"
    sanitized: bool = True
    retention_policy: str = "local_debug"
    content_hash: str | None = None


@dataclass
class OfferCandidate:
    source_name: str
    retailer: str
    listing_url: str
    title: str
    base_price: float | None = None
    shipping_price: float | None = None
    effective_price: float | None = None
    condition: str | None = None
    availability: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    evidence_snapshot: EvidenceSnapshot | None = None
    source_role: str = "truth"
    verification_state: str = "unverified"
    extraction_confidence: str | None = None


@dataclass
class RankedOffer:
    offer: OfferCandidate
    score: float
    label: str | None = None
    reasons: list[str] = field(default_factory=list)


@dataclass
class StructuredIntake:
    user_query: UserQuery
    parsed_intent: ParsedIntent
    product_intent: ProductIntent
    watch_rule: WatchRule | None = None


@dataclass
class ExecutionResult:
    intent_type: str
    category: str | None
    ranked_offers: list[RankedOffer] = field(default_factory=list)
    recent_searches: list[dict[str, Any]] = field(default_factory=list)
    watch_items: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    budget_summary: dict[str, Any] = field(default_factory=dict)
    message: str | None = None
