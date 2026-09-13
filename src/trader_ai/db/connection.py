"""SQLite connection helpers.

The only module that knows where the schema lives or which PRAGMAs matter.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection with foreign keys enforced and rows as mappings."""
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def apply_schema(con: sqlite3.Connection) -> None:
    """Create all tables/indexes. Safe to call on a fresh database only."""
    con.executescript(SCHEMA_PATH.read_text())
    con.commit()


SCHEMA_V02_PATH = Path(__file__).with_name("schema_v02.sql")


def apply_schema_v02(con: sqlite3.Connection) -> None:
    """Apply the additive v0.2 migration. Requires apply_schema first."""
    con.executescript(SCHEMA_V02_PATH.read_text())
    con.commit()
