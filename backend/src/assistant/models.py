"""Domain models. Kept independent of SQLite so a later Supabase adapter can reuse them."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


@dataclass
class Task:
    id: str
    title: str
    description: str
    category: str
    due_date: date
    status: str = "open"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    source: str = "user"

    def to_legacy_dict(self) -> dict[str, str]:
        """Shape used by the original CLI and CSV-era tests."""
        return {
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "due_date": self.due_date.isoformat(),
        }
