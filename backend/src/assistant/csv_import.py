"""One-shot import of the original tasks.csv into SQLite."""

from __future__ import annotations

import csv
import logging
from datetime import date
from pathlib import Path

from assistant.services.tasks import TaskService

logger = logging.getLogger(__name__)


def import_tasks_csv(path: Path | str, service: TaskService) -> int:
    """
    Import rows from a CSV with columns title, description, category, due_date.

    Returns the number of tasks inserted. Does not skip duplicates; callers
    should only run this when the task table is empty.
    """
    csv_path = Path(path)
    if not csv_path.is_file():
        raise FileNotFoundError(str(csv_path))

    inserted = 0
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            title = (row.get("title") or "").strip()
            if not title:
                continue
            due_raw = (row.get("due_date") or "").strip()
            due = date.fromisoformat(due_raw)
            service.add_task(
                title=title,
                description=(row.get("description") or "").strip(),
                category=(row.get("category") or "Other").strip() or "Other",
                due_date=due,
                source="csv_import",
            )
            inserted += 1

    logger.info("Imported %s task(s) from %s", inserted, csv_path)
    return inserted


def import_if_empty(path: Path | str, service: TaskService) -> int:
    csv_path = Path(path)
    if service.is_empty() and csv_path.is_file():
        return import_tasks_csv(csv_path, service)
    return 0
