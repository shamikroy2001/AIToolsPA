"""Sequential schema migrations with an applied-version table and PRAGMA user_version."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL,
            due_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'user'
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks (due_date);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status);
        CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks (category);
        CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks (created_at);
        """,
    ),
]


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def current_version(conn: sqlite3.Connection) -> int:
    _ensure_migrations_table(conn)
    row = conn.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
    if row is None or row["version"] is None:
        return 0
    return int(row["version"])


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Apply all pending migrations. Returns the resulting schema version."""
    _ensure_migrations_table(conn)
    applied = current_version(conn)
    now = datetime.now(timezone.utc).isoformat()

    for version, sql in MIGRATIONS:
        if version <= applied:
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, now),
        )
        conn.execute(f"PRAGMA user_version = {int(version)}")
        applied = version

    conn.commit()
    return applied
