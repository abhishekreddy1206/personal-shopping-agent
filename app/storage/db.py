from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_schema(conn: sqlite3.Connection, schema_path: str | Path) -> None:
    schema_sql = Path(schema_path).read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()
    _apply_additive_migrations(conn)


def _apply_additive_migrations(conn: sqlite3.Connection) -> None:
    """Apply lightweight, idempotent ALTERs for columns added after a database was first
    created. CREATE TABLE IF NOT EXISTS won't add new columns to an existing table —
    these explicit ALTERs cover that case. Each migration is wrapped in a try/except so
    re-running is safe.
    """
    additive_columns = [
        # (table, column_definition)
        ("watch_rules", "category TEXT"),
    ]
    for table, column_def in additive_columns:
        column_name = column_def.split()[0]
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column_name in existing:
            continue
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
            conn.commit()
        except sqlite3.OperationalError:
            # Column was added concurrently or table doesn't exist yet — safe to ignore.
            pass
