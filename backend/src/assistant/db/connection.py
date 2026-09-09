"""SQLite connection factory and database initialization."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from assistant.db.migrate import apply_migrations


def connect(database_path: Path | str) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize_database(database_path: Path | str) -> sqlite3.Connection:
    """Open (or create) the database and apply pending migrations."""
    conn = connect(database_path)
    apply_migrations(conn)
    return conn
