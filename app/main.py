from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage.db import connect, initialize_schema
from app.storage.repository import Repository
from app.telegram.handler import TelegramHandler
from app.watchlist.scheduler import WatchlistScheduler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Personal shopping agent local runner")
    parser.add_argument("query", nargs="*", help="Shopping query or command")
    parser.add_argument("--db", dest="db_path", help="Optional SQLite DB path")
    parser.add_argument("--watch-check", action="store_true", help="Run watchlist check cycle")
    return parser


def bootstrap_query(query_parts: list[str]) -> str:
    if query_parts:
        return " ".join(query_parts)
    return "Find me the best deal on Sony WH-1000XM6"


def resolve_db_path(db_path: str | None) -> Path:
    return Path(db_path) if db_path else ROOT / "data" / "db" / "shopping_agent.db"


def run_watch_check(db_path: Path) -> dict:
    conn = connect(db_path)
    try:
        initialize_schema(conn, ROOT / "data" / "db" / "schema.sql")
        repository = Repository(conn)
        scheduler = WatchlistScheduler(repository)
        return {"watch_check_results": scheduler.run_pending_checks()}
    finally:
        conn.close()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    db_path = resolve_db_path(args.db_path)

    if args.watch_check:
        print(json.dumps(run_watch_check(db_path), indent=2))
        return 0

    query = bootstrap_query(args.query)
    handler = TelegramHandler(db_path=str(db_path))
    try:
        result = handler.handle_message(query)
        print(json.dumps(result, indent=2))
    finally:
        handler.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
