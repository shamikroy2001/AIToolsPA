"""Create core tables through asyncpg when Alembic has not applied yet."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import inspect, text

import app.models  # noqa: F401
from app.core.db import get_admin_engine, get_app_engine
from app.models.base import Base

log = logging.getLogger("app.schema")

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _alembic_head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(Config(str(_ALEMBIC_INI))).get_current_head()


def missing_relation(exc: BaseException) -> bool:
    blob = f"{type(exc).__name__} {exc}".lower()
    return "undefinedtable" in blob or "does not exist" in blob


async def ensure_core_schema() -> None:
    engine = get_admin_engine() or get_app_engine()
    if engine is None:
        raise RuntimeError("database engine is not configured")

    async with engine.begin() as conn:

        def _needs_create(sync_conn) -> bool:
            return not inspect(sync_conn).has_table("plans")

        if not await conn.run_sync(_needs_create):
            return
        log.warning("plans table missing; creating schema over asyncpg")
        await conn.run_sync(Base.metadata.create_all)
        head = _alembic_head()
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version ("
                "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        existing = await conn.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
        if existing is None and head:
            await conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
                {"rev": head},
            )
            log.info("Stamped alembic_version at %s", head)
