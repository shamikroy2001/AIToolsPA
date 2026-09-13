"""Regression: unhandled errors must be JSON + logged, and ask must not 500.

Staging curl of POST /api/tasks returned Starlette's 21-byte text/plain
`Internal Server Error` with no traceback (Alembic fileConfig disabled
uvicorn.error). Catalog INSERT as pa_app was a separate ask-path footgun.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.ai.fake import FakeAIProvider
from app.ai.types import GenerateRequest, GenerateResult
from app.core.plan_catalog import DEFAULT_PLANS
from app.models.assistant import AssistantProfile, AssistantTask, TaskCost
from app.models.base import Base
from app.models.plan import Plan
from app.models.user import User
from app.services.assistant import AssistantService
from app.services.credits import CreditService
from conftest import TOKEN_A


def _auth(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _allocate_pro(client: TestClient, user_id: str, event_id: str = "evt_ask") -> None:
    start = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
    client.post(
        "/api/webhooks/stripe",
        json={
            "id": event_id,
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": f"sub_{event_id}",
                    "customer": f"cus_{event_id}",
                    "status": "active",
                    "current_period_start": start,
                    "current_period_end": end,
                    "items": {"data": [{"price": {"id": "price_pro"}}]},
                    "metadata": {"user_id": user_id},
                }
            },
        },
    )


def _assert_no_ai_leak(payload: object) -> None:
    text = str(payload).lower()
    for forbidden in ("provider", "model", "tokens", "gemini", "openai", "gateway"):
        assert forbidden not in text


class _BoomProvider:
    async def generate(self, request: GenerateRequest) -> GenerateResult:
        del request
        raise RuntimeError("simulated provider crash")


@pytest.fixture
async def ask_session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _user_with_credits(session: AsyncSession) -> User:
    seed = next(p for p in DEFAULT_PLANS if p["slug"] == "pro")
    plan = Plan(**seed)
    user = User(id=uuid4(), clerk_user_id="clerk_ask", email="ask@example.com", plan="pro")
    session.add(plan)
    session.add(user)
    await session.flush()
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 1, tzinfo=timezone.utc)
    await CreditService(session).allocate_period(user, plan, start, end, now=start)
    return user


@pytest.mark.asyncio
async def test_ask_succeeds_when_task_cost_insert_is_denied(ask_session: AsyncSession):
    """pa_app cannot INSERT task_costs; a missing/hidden catalog row must not 500."""
    user = await _user_with_credits(ask_session)
    original_add = ask_session.add

    def deny_catalog_writes(obj) -> None:
        if isinstance(obj, TaskCost):
            raise RuntimeError("permission denied for table task_costs")
        original_add(obj)

    ask_session.add = deny_catalog_writes  # type: ignore[method-assign]
    service = AssistantService(ask_session, FakeAIProvider(text="D1 gate ok"))
    task = await service.ask(user, "Reply with exactly: D1 gate ok")
    assert task.status == "completed"
    assert task.credits_charged == 5
    assert (await ask_session.scalar(select(TaskCost))) is None
    stored = await ask_session.get(AssistantTask, task.id)
    assert stored is not None
    assert '"reply": "D1 gate ok"' in (stored.output_data or "")


@pytest.mark.asyncio
async def test_ask_succeeds_when_profile_insert_is_denied(ask_session: AsyncSession):
    """Tenant INSERT on assistant_profiles must not block ask (admin upserts the row)."""
    user = await _user_with_credits(ask_session)
    original_add = ask_session.add

    def deny_profile_writes(obj) -> None:
        if isinstance(obj, AssistantProfile):
            raise RuntimeError("permission denied for table assistant_profiles")
        original_add(obj)

    ask_session.add = deny_profile_writes  # type: ignore[method-assign]
    service = AssistantService(ask_session, FakeAIProvider(text="D1 gate ok"))
    task = await service.ask(user, "Reply with exactly: D1 gate ok")
    assert task.status == "completed"
    assert (await ask_session.scalar(select(AssistantProfile))) is None


def test_assistant_profile_timestamps_are_timezone_aware():
    assert AssistantProfile.__table__.c.created_at.type.timezone is True
    assert AssistantProfile.__table__.c.updated_at.type.timezone is True
    assert AssistantTask.__table__.c.created_at.type.timezone is True
    assert AssistantTask.__table__.c.completed_at.type.timezone is True


def test_provider_crash_is_json_503_with_cors(saas_client: TestClient):
    from app.ai import set_ai_provider

    set_ai_provider(_BoomProvider())
    me = saas_client.get("/api/me", headers=_auth()).json()
    _allocate_pro(saas_client, me["id"], "evt_boom")
    origin = "http://localhost:3000"
    before = saas_client.get("/api/credits", headers=_auth()).json()["available"]
    response = saas_client.post(
        "/api/tasks",
        json={"message": "Hello"},
        headers={**_auth(), "Origin": origin},
    )
    assert response.status_code == 503
    assert response.headers.get("content-type", "").startswith("application/json")
    assert response.headers.get("access-control-allow-origin") == origin
    body = response.json()
    assert "unavailable" in body["detail"].lower()
    _assert_no_ai_leak(body)
    after = saas_client.get("/api/credits", headers=_auth()).json()["available"]
    assert after == before
    assert saas_client.get("/api/tasks", headers=_auth()).json() == []
    set_ai_provider(FakeAIProvider())


@pytest.mark.asyncio
async def test_get_or_create_profile_returns_defaults_when_insert_denied(
    ask_session: AsyncSession,
):
    user = await _user_with_credits(ask_session)
    original_add = ask_session.add

    def deny_profile_writes(obj) -> None:
        if isinstance(obj, AssistantProfile):
            raise RuntimeError("permission denied for table assistant_profiles")
        original_add(obj)

    ask_session.add = deny_profile_writes  # type: ignore[method-assign]
    service = AssistantService(ask_session, FakeAIProvider())
    profile = await service.get_or_create_profile(user.id)
    assert profile.assistant_name == "Assistant"
    assert profile.user_id == user.id
    assert profile.timezone == "UTC"


def test_assistant_profile_model_matches_alembic_0003():
    """Alembic 0003 created timestamptz + a timezone column; the ORM must match."""
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable

    cols = set(AssistantProfile.__table__.c.keys())
    assert cols == {
        "id",
        "user_id",
        "assistant_name",
        "personality",
        "response_style",
        "timezone",
        "language",
        "created_at",
        "updated_at",
    }
    assert AssistantProfile.__table__.c.timezone.name == "timezone"
    ddl = str(CreateTable(AssistantProfile.__table__).compile(dialect=postgresql.dialect()))
    assert "TIMESTAMP WITH TIME ZONE" in ddl
    assert '"timezone"' in ddl


def test_get_admin_db_sets_tenant_guc():
    import inspect

    from app.api.deps import get_admin_db

    source = inspect.getsource(get_admin_db)
    assert "apply_tenant" in source
    assert "get_current_user" in source


def test_unhandled_ask_error_is_json_500_with_cors(
    saas_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from app.services.assistant import AssistantService

    async def boom(self, task_type):
        del self, task_type
        raise RuntimeError("simulated cost failure")

    monkeypatch.setattr(AssistantService, "estimate_cost", boom)
    me = saas_client.get("/api/me", headers=_auth()).json()
    _allocate_pro(saas_client, me["id"], "evt_unhandled")
    origin = "http://localhost:3000"
    before = saas_client.get("/api/credits", headers=_auth()).json()["available"]
    response = saas_client.post(
        "/api/tasks",
        json={"message": "Hello"},
        headers={**_auth(), "Origin": origin},
    )
    assert response.status_code == 500
    assert response.headers.get("content-type", "").startswith("application/json")
    assert response.headers.get("access-control-allow-origin") == origin
    body = response.json()
    assert body["detail"] == "Something went wrong. Try again shortly."
    _assert_no_ai_leak(body)
    after = saas_client.get("/api/credits", headers=_auth()).json()["available"]
    assert after == before
    assert saas_client.get("/api/tasks", headers=_auth()).json() == []


def test_unhandled_error_is_json_not_starlette_plaintext(
    saas_client: TestClient, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
):
    """Direct curl (no CORS) must not see text/plain Internal Server Error."""
    import logging

    from app.api.deps import set_token_verifier

    class BoomVerifier:
        def verify(self, token: str) -> None:
            del token
            raise RuntimeError("simulated verifier crash")

    set_token_verifier(BoomVerifier())
    caplog.set_level(logging.ERROR)
    origin = "http://localhost:3000"
    # JsonErrorMiddleware swallows; ServerErrorMiddleware never emits text/plain.
    response = saas_client.get("/api/me", headers={**_auth(), "Origin": origin})
    assert response.status_code == 500
    assert response.headers.get("content-type", "").startswith("application/json")
    assert response.content != b"Internal Server Error"
    assert response.text.strip() != "Internal Server Error"
    assert response.headers.get("access-control-allow-origin") == origin
    body = response.json()
    assert body["detail"] == "Something went wrong. Try again shortly."
    _assert_no_ai_leak(body)
    combined = caplog.text + capsys.readouterr().err
    assert "simulated verifier crash" in combined
    assert "Unhandled error" in combined


def test_configure_app_logging_reenables_disabled_loggers():
    import logging

    from app.core.logging import configure_app_logging

    silenced = logging.getLogger("uvicorn.error")
    silenced.disabled = True
    silenced.setLevel(logging.WARNING)
    configure_app_logging("INFO")
    assert silenced.disabled is False
    assert silenced.level <= logging.INFO
