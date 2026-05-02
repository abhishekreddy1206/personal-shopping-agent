from __future__ import annotations

from typing import Optional

from app.integration_runner import handle_text, handle_watch_check


SHOPPING_KEYWORDS = [
    "deal",
    "best price",
    "best deal",
    "track this",
    "watchlist",
    "price drop",
    "coupon",
    "monitor",
    "headphones",
    "running shoes",
    "ebay",
    "marketplace",
    "slickdeals",
    "buy now",
    "wait",
]


def should_handle(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in SHOPPING_KEYWORDS)


def handle_message(text: str, db_path: Optional[str] = None) -> str:
    return handle_text(text, db_path=db_path)


def handle_scheduled_watch_check(db_path: Optional[str] = None) -> str:
    return handle_watch_check(db_path=db_path)
