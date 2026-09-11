import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.main import lifespan
from start_api import listen_port, start_migrations


def test_listen_port_reads_railway_port(monkeypatch):
    monkeypatch.setenv("PORT", "8080")
    assert listen_port() == 8080


def test_listen_port_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("PORT", "${PORT}")
    assert listen_port() == 8000


def test_start_migrations_does_not_block_when_alembic_hangs(monkeypatch):
    monkeypatch.setattr("start_api.run_migrations", lambda: __import__("time").sleep(30))
    start_migrations(wait_seconds=0.1)


@pytest.mark.asyncio
async def test_lifespan_yields_before_plan_seed_finishes(monkeypatch):
    started = asyncio.Event()

    class HangingSession:
        async def __aenter__(self):
            started.set()
            await asyncio.sleep(3600)
            return MagicMock()

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr("app.main.init_engines_from_settings", lambda: None)
    monkeypatch.setattr("app.main.get_app_engine", lambda: None)
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: SimpleNamespace(environment="staging"),
    )
    monkeypatch.setattr("app.main.admin_session_factory", lambda: HangingSession)

    yielded = False
    async with lifespan(MagicMock()):
        yielded = True
        await asyncio.sleep(0)
        assert started.is_set()

    assert yielded
