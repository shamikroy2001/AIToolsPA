"""Process-wide database and TaskService wiring for the CLI."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from assistant.config import clear_settings_cache, get_settings
from assistant.csv_import import import_if_empty
from assistant.db.connection import initialize_database
from assistant.logging_config import configure_logging
from assistant.repositories.tasks import SqliteTaskRepository
from assistant.services.tasks import TaskService

_override: TaskService | None = None
_service: TaskService | None = None
_connection: sqlite3.Connection | None = None


def set_task_service(service: TaskService | None) -> None:
    """Tests inject a temp-database service so the CLI never touches data/assistant.db."""
    global _override
    _override = service


def reset_runtime() -> None:
    global _service, _connection, _override
    if _connection is not None:
        _connection.close()
    _connection = None
    _service = None
    _override = None
    clear_settings_cache()


def get_task_service() -> TaskService:
    if _override is not None:
        return _override
    if _service is not None:
        return _service
    return _build_default_service()


def _build_default_service() -> TaskService:
    global _service, _connection
    settings = get_settings()
    configure_logging(settings.log_level)
    _connection = initialize_database(settings.database_path)
    _service = TaskService(SqliteTaskRepository(_connection))
    csv_path = _legacy_csv_path()
    if csv_path is not None:
        import_if_empty(csv_path, _service)
    return _service


def _legacy_csv_path() -> Path | None:
    repo_root = Path(__file__).resolve().parents[3]
    for candidate in (Path("tasks.csv"), repo_root / "tasks.csv"):
        if candidate.is_file():
            return candidate
    return None
