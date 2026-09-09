"""Shared fixtures. CLI tests inject a temp SQLite database; SaaS tests use sqlite + fake Stripe."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai import set_ai_provider
from app.ai.fake import FakeAIProvider
from app.api.deps import set_token_verifier
from app.core.auth import StaticTokenVerifier
from app.core.principals import ClerkPrincipal
from app.core.settings import clear_settings_cache
from app.services.stripe_gateway import FakeStripeGateway, set_stripe_gateway
from assistant.db.connection import initialize_database
from assistant.repositories.tasks import SqliteTaskRepository
from assistant.runtime import reset_runtime, set_task_service
from assistant.services.tasks import TaskService

TOKEN_A = "token-user-a"
TOKEN_B = "token-user-b"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "assistant.db"


@pytest.fixture
def conn(db_path: Path):
    connection = initialize_database(db_path)
    yield connection
    connection.close()


@pytest.fixture
def repo(conn):
    return SqliteTaskRepository(conn)


@pytest.fixture
def service(repo) -> TaskService:
    return TaskService(repo)


@pytest.fixture
def seeded_service(service: TaskService) -> TaskService:
    service.add_task("Test Task", "Test Desc", "Work", date(2024, 9, 30))
    return service


@pytest.fixture
def isolated_cli(seeded_service: TaskService):
    """Make project.py functions use the temp database instead of data/assistant.db."""
    reset_runtime()
    set_task_service(seeded_service)
    yield seeded_service
    reset_runtime()


@pytest.fixture
def fake_stripe() -> FakeStripeGateway:
    gateway = FakeStripeGateway()
    set_stripe_gateway(gateway)
    yield gateway
    set_stripe_gateway(None)


@pytest.fixture
def saas_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_stripe: FakeStripeGateway):
    db_file = tmp_path / "saas.db"
    url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("DATABASE_ADMIN_URL", url)
    monkeypatch.setenv("STRIPE_BASIC_PRICE_ID", "price_basic")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro")
    monkeypatch.setenv("STRIPE_PREMIUM_PRICE_ID", "price_premium")
    monkeypatch.setenv("PUBLIC_APP_URL", "http://localhost:3000")
    clear_settings_cache()
    set_ai_provider(FakeAIProvider())
    set_token_verifier(
        StaticTokenVerifier(
            {
                TOKEN_A: ClerkPrincipal(clerk_user_id="clerk_a", email="a@example.com"),
                TOKEN_B: ClerkPrincipal(clerk_user_id="clerk_b", email="b@example.com"),
            }
        )
    )
    from app.main import app

    with TestClient(app) as client:
        yield client
    set_token_verifier(None)
    set_ai_provider(None)
    clear_settings_cache()
    del fake_stripe
