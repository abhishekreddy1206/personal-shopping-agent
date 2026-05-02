from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formatting import format_result, format_watch_check
from app.main import resolve_db_path, run_watch_check
from app.telegram.handler import TelegramHandler


def handle_text(text: str, db_path: str | None = None) -> str:
    handler = TelegramHandler(db_path=db_path)
    try:
        payload = handler.handle_message(text)
        return format_result(payload)
    finally:
        handler.close()


def handle_watch_check(db_path: str | None = None) -> str:
    payload = run_watch_check(resolve_db_path(db_path))
    return format_watch_check(payload)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--watch-check":
        print(handle_watch_check())
    else:
        text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Find me the best deal on Sony WH-1000XM6"
        print(handle_text(text))
