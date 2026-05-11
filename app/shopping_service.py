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


def handle_message(text: str, db_path: Optional[str] = None, conversation_key: Optional[str] = None) -> str:
    """Babji entry point. `conversation_key` is optional today (single-user installs
    use the default); pass a per-Telegram-chat key when the integration starts
    forwarding it so multi-chat clarifications stay isolated."""
    return handle_text(text, db_path=db_path, conversation_key=conversation_key)


def handle_scheduled_watch_check(db_path: Optional[str] = None) -> str:
    return handle_watch_check(db_path=db_path)
