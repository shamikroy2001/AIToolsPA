"""Task persistence. SqliteTaskRepository is the current adapter; TaskRepository is the port."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Protocol

from assistant.models import Task, new_id, utc_now


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _row_to_task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        category=row["category"],
        due_date=_parse_date(row["due_date"]),
        status=row["status"],
        created_at=_parse_datetime(row["created_at"]),
        updated_at=_parse_datetime(row["updated_at"]),
        source=row["source"],
    )


class TaskRepository(Protocol):
    def add(self, task: Task) -> Task: ...

    def get(self, task_id: str) -> Task | None: ...

    def list_all(self) -> list[Task]: ...

    def count(self) -> int: ...

    def update(self, task: Task) -> Task: ...

    def delete(self, task_id: str) -> bool: ...


class SqliteTaskRepository:
    """SQLite adapter. List order is created_at, id — same insertion order as the old CSV."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, task: Task) -> Task:
        now = utc_now()
        created = task.created_at or now
        updated = task.updated_at or now
        task_id = task.id or new_id()
        stored = Task(
            id=task_id,
            title=task.title,
            description=task.description,
            category=task.category,
            due_date=task.due_date,
            status=task.status,
            created_at=created,
            updated_at=updated,
            source=task.source,
        )
        self._conn.execute(
            """
            INSERT INTO tasks (
                id, title, description, category, due_date,
                status, created_at, updated_at, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stored.id,
                stored.title,
                stored.description,
                stored.category,
                stored.due_date.isoformat(),
                stored.status,
                stored.created_at.isoformat(),
                stored.updated_at.isoformat(),
                stored.source,
            ),
        )
        self._conn.commit()
        return stored

    def get(self, task_id: str) -> Task | None:
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_task(row)

    def list_all(self) -> list[Task]:
        rows = self._conn.execute(
            "SELECT * FROM tasks ORDER BY created_at ASC, id ASC"
        ).fetchall()
        return [_row_to_task(row) for row in rows]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()
        return int(row["n"]) if row else 0

    def update(self, task: Task) -> Task:
        updated = utc_now()
        stored = Task(
            id=task.id,
            title=task.title,
            description=task.description,
            category=task.category,
            due_date=task.due_date,
            status=task.status,
            created_at=task.created_at,
            updated_at=updated,
            source=task.source,
        )
        cursor = self._conn.execute(
            """
            UPDATE tasks
            SET title = ?, description = ?, category = ?, due_date = ?,
                status = ?, updated_at = ?, source = ?
            WHERE id = ?
            """,
            (
                stored.title,
                stored.description,
                stored.category,
                stored.due_date.isoformat(),
                stored.status,
                stored.updated_at.isoformat(),
                stored.source,
                stored.id,
            ),
        )
        self._conn.commit()
        if cursor.rowcount == 0:
            raise KeyError(f"Task not found: {task.id}")
        return stored

    def delete(self, task_id: str) -> bool:
        cursor = self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._conn.commit()
        return cursor.rowcount > 0
