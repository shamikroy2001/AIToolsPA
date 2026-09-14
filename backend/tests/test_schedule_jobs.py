"""Gmail analyze + Telegram notify schedule jobs: success and fail-soft skips."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import undefer
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.crypto import decrypt_json, encrypt_json
from app.core.settings import clear_settings_cache
from app.models.assistant import TaskCost
from app.models.automation import Integration, Notification, ScheduledTask
from app.models.base import Base
from app.models.credit import SOURCE_MONTHLY, CreditLot, CreditTransaction
from app.models.user import User
from app.services.credits import CreditService
from app.services.gmail import GmailService, format_mail_summary
from app.services.monitor_poll import poll_due_monitors_in_session, process_scheduled_task
from app.services.telegram import TelegramService


NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
MOCK_ACCESS = "ya29.mock-access-token"
MOCK_REFRESH = "1//mock-refresh-token"
MOCK_BOT = "111111:AA-test-bot-secret"
MOCK_CHAT = "42424242"
FERNET_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", FERNET_KEY)
    monkeypatch.setenv("GMAIL_CLIENT_ID", "client-id")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", MOCK_BOT)
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


async def _user_with_credits(session: AsyncSession, amount: int = 40) -> User:
    user = User(id=uuid4(), clerk_user_id=f"clerk_{uuid4().hex[:8]}", email="s@example.com")
    session.add(user)
    for task_type, base, maximum in (
        ("gmail_analyze", 8, 40),
        ("telegram_notify", 1, 5),
        ("website_monitor", 3, 15),
    ):
        existing = await session.scalar(select(TaskCost).where(TaskCost.task_type == task_type))
        if existing is None:
            session.add(
                TaskCost(
                    task_type=task_type,
                    base_credit_cost=base,
                    minimum_cost=1,
                    maximum_cost=maximum,
                    enabled=True,
                )
            )
    if amount:
        session.add(
            CreditLot(
                user_id=user.id,
                source=SOURCE_MONTHLY,
                original_amount=amount,
                remaining_amount=amount,
                billing_period="2026-09",
                expires_at=None,
            )
        )
    await session.flush()
    return user


async def _connect(
    session: AsyncSession,
    user: User,
    provider: str,
    credentials: dict[str, Any],
) -> Integration:
    row = Integration(
        user_id=user.id,
        provider=provider,
        status="connected",
        encrypted_credentials=encrypt_json(credentials),
    )
    session.add(row)
    await session.flush()
    return row


async def _schedule(
    session: AsyncSession,
    user: User,
    task_type: str,
    *,
    cadence: str = "daily",
    payload: str = "{}",
    next_run_at: datetime | None = None,
) -> ScheduledTask:
    row = ScheduledTask(
        user_id=user.id,
        task_type=task_type,
        cadence=cadence,
        payload=payload,
        enabled=True,
        next_run_at=next_run_at if next_run_at is not None else NOW - timedelta(hours=1),
    )
    session.add(row)
    await session.flush()
    return row


def _assert_no_secrets(payload: object, *extra: str) -> None:
    text = str(payload).lower()
    for forbidden in (
        "encrypted_credentials",
        "refresh_token",
        "access_token",
        "client_secret",
        "bot_token",
        MOCK_ACCESS.lower(),
        MOCK_REFRESH.lower(),
        MOCK_BOT.lower(),
        "aa-test-bot-secret",
        MOCK_CHAT,
        *extra,
    ):
        assert forbidden not in text


def _ok_gmail(summary: str = "2 recent message(s):\n- Invoice\n- Hello"):
    async def _inner(credentials: dict[str, Any], payload: dict[str, Any]):
        assert credentials["access_token"] == MOCK_ACCESS
        assert "query" in payload or payload == {} or isinstance(payload, dict)
        return summary, credentials

    return _inner


def _fail_gmail():
    async def _inner(credentials: dict[str, Any], payload: dict[str, Any]):
        del credentials, payload
        return None

    return _inner


def _ok_telegram(calls: list[tuple[str, str]] | None = None):
    async def _inner(credentials: dict[str, Any], message: str) -> bool:
        if calls is not None:
            calls.append((str(credentials.get("chat_id")), message))
        return True

    return _inner


def _fail_telegram():
    async def _inner(credentials: dict[str, Any], message: str) -> bool:
        del credentials, message
        return False

    return _inner


@pytest.mark.asyncio
async def test_gmail_analyze_success_notifies_charges_and_advances(session: AsyncSession):
    user = await _user_with_credits(session, amount=40)
    await _connect(
        session,
        user,
        "gmail",
        {
            "access_token": MOCK_ACCESS,
            "refresh_token": MOCK_REFRESH,
            "email": "reader@example.com",
        },
    )
    task = await _schedule(session, user, "gmail_analyze")
    credits = CreditService(session)
    before = await credits.available(user.id, now=NOW)

    result = await process_scheduled_task(
        session, task, now=NOW, gmail_analyze=_ok_gmail()
    )

    assert result.advanced is True
    assert result.charged is True
    assert result.notified is True
    assert task.next_run_at == NOW + timedelta(days=1)
    assert await credits.available(user.id, now=NOW) == before - 8
    txs = list(
        (
            await session.scalars(
                select(CreditTransaction).where(
                    CreditTransaction.user_id == user.id,
                    CreditTransaction.description == "gmail_analyze",
                )
            )
        ).all()
    )
    assert sum(row.amount for row in txs) == -8
    notices = list(
        (await session.scalars(select(Notification).where(Notification.user_id == user.id))).all()
    )
    assert len(notices) == 1
    assert notices[0].channel == "in_app"
    assert notices[0].title == "Gmail summary"
    assert "Invoice" in notices[0].body
    _assert_no_secrets(notices[0].title + notices[0].body)


@pytest.mark.asyncio
async def test_gmail_skips_when_not_connected(session: AsyncSession):
    user = await _user_with_credits(session)
    task = await _schedule(session, user, "gmail_analyze")
    due = task.next_run_at
    calls: list[str] = []

    async def analyze(credentials, payload):
        calls.append("ran")
        return "should not run", credentials

    result = await process_scheduled_task(session, task, now=NOW, gmail_analyze=analyze)
    assert result.skipped_reason == "not_connected"
    assert result.advanced is False
    assert task.next_run_at == due
    assert calls == []
    assert (await session.scalars(select(Notification))).all() == []


@pytest.mark.asyncio
async def test_gmail_skips_when_disconnected(session: AsyncSession):
    user = await _user_with_credits(session)
    await _connect(
        session,
        user,
        "gmail",
        {"access_token": MOCK_ACCESS, "refresh_token": MOCK_REFRESH},
    )
    row = await session.scalar(select(Integration).where(Integration.user_id == user.id))
    assert row is not None
    row.status = "disconnected"
    row.encrypted_credentials = ""
    await session.flush()
    task = await _schedule(session, user, "gmail_analyze")
    due = task.next_run_at

    result = await process_scheduled_task(
        session, task, now=NOW, gmail_analyze=_ok_gmail()
    )
    assert result.skipped_reason == "not_connected"
    assert task.next_run_at == due


@pytest.mark.asyncio
async def test_gmail_insufficient_credits_skips_without_provider_call(session: AsyncSession):
    user = await _user_with_credits(session, amount=3)
    await _connect(
        session,
        user,
        "gmail",
        {"access_token": MOCK_ACCESS, "refresh_token": MOCK_REFRESH},
    )
    task = await _schedule(session, user, "gmail_analyze")
    due = task.next_run_at
    calls: list[str] = []

    async def analyze(credentials, payload):
        calls.append("ran")
        return "nope", credentials

    result = await process_scheduled_task(session, task, now=NOW, gmail_analyze=analyze)
    assert result.skipped_reason == "insufficient_credits"
    assert result.charged is False
    assert task.next_run_at == due
    assert calls == []
    assert await CreditService(session).available(user.id, now=NOW) == 3


@pytest.mark.asyncio
async def test_gmail_provider_failure_leaves_schedule_due(session: AsyncSession):
    user = await _user_with_credits(session)
    await _connect(
        session,
        user,
        "gmail",
        {"access_token": MOCK_ACCESS, "refresh_token": MOCK_REFRESH},
    )
    task = await _schedule(session, user, "gmail_analyze")
    due = task.next_run_at
    before = await CreditService(session).available(user.id, now=NOW)

    result = await process_scheduled_task(
        session, task, now=NOW, gmail_analyze=_fail_gmail()
    )
    assert result.skipped_reason == "provider_error"
    assert result.advanced is False
    assert task.next_run_at == due
    assert await CreditService(session).available(user.id, now=NOW) == before
    assert (await session.scalars(select(Notification))).all() == []


@pytest.mark.asyncio
async def test_telegram_notify_success_sends_charges_and_advances(session: AsyncSession):
    user = await _user_with_credits(session, amount=10)
    await _connect(session, user, "telegram", {"chat_id": MOCK_CHAT, "username": "alice"})
    task = await _schedule(
        session,
        user,
        "telegram_notify",
        cadence="hourly",
        payload='{"message":"Standup in 10 minutes"}',
    )
    sent: list[tuple[str, str]] = []
    before = await CreditService(session).available(user.id, now=NOW)

    result = await process_scheduled_task(
        session, task, now=NOW, telegram_send=_ok_telegram(sent)
    )

    assert result.advanced is True
    assert result.charged is True
    assert sent == [(MOCK_CHAT, "Standup in 10 minutes")]
    assert task.next_run_at == NOW + timedelta(hours=1)
    assert await CreditService(session).available(user.id, now=NOW) == before - 1
    notices = list(
        (await session.scalars(select(Notification).where(Notification.user_id == user.id))).all()
    )
    assert len(notices) == 1
    assert "Standup in 10 minutes" in notices[0].body
    _assert_no_secrets(notices[0].title + notices[0].body)


@pytest.mark.asyncio
async def test_telegram_skips_when_not_connected(session: AsyncSession):
    user = await _user_with_credits(session)
    task = await _schedule(session, user, "telegram_notify")
    due = task.next_run_at
    calls: list[str] = []

    async def send(credentials, message):
        calls.append("ran")
        return True

    result = await process_scheduled_task(session, task, now=NOW, telegram_send=send)
    assert result.skipped_reason == "not_connected"
    assert task.next_run_at == due
    assert calls == []


@pytest.mark.asyncio
async def test_telegram_insufficient_credits_skips_without_send(session: AsyncSession):
    user = await _user_with_credits(session, amount=0)
    await _connect(session, user, "telegram", {"chat_id": MOCK_CHAT, "username": "alice"})
    task = await _schedule(session, user, "telegram_notify")
    due = task.next_run_at
    calls: list[str] = []

    async def send(credentials, message):
        calls.append("ran")
        return True

    result = await process_scheduled_task(session, task, now=NOW, telegram_send=send)
    assert result.skipped_reason == "insufficient_credits"
    assert task.next_run_at == due
    assert calls == []


@pytest.mark.asyncio
async def test_telegram_provider_failure_leaves_schedule_due(session: AsyncSession):
    user = await _user_with_credits(session)
    await _connect(session, user, "telegram", {"chat_id": MOCK_CHAT, "username": "alice"})
    task = await _schedule(session, user, "telegram_notify")
    due = task.next_run_at
    before = await CreditService(session).available(user.id, now=NOW)

    result = await process_scheduled_task(
        session, task, now=NOW, telegram_send=_fail_telegram()
    )
    assert result.skipped_reason == "provider_error"
    assert task.next_run_at == due
    assert await CreditService(session).available(user.id, now=NOW) == before


@pytest.mark.asyncio
async def test_provider_failure_does_not_block_other_schedules(session: AsyncSession):
    user = await _user_with_credits(session)
    await _connect(
        session,
        user,
        "gmail",
        {"access_token": MOCK_ACCESS, "refresh_token": MOCK_REFRESH},
    )
    await _connect(session, user, "telegram", {"chat_id": MOCK_CHAT, "username": "alice"})
    gmail = await _schedule(session, user, "gmail_analyze")
    telegram = await _schedule(session, user, "telegram_notify", cadence="hourly")
    gmail_due = gmail.next_run_at

    await poll_due_monitors_in_session(
        session,
        now=NOW,
        gmail_analyze=_fail_gmail(),
        telegram_send=_ok_telegram(),
    )

    await session.refresh(gmail)
    await session.refresh(telegram)
    assert gmail.next_run_at == gmail_due
    assert telegram.next_run_at == NOW + timedelta(hours=1)
    notices = list(
        (await session.scalars(select(Notification).where(Notification.user_id == user.id))).all()
    )
    assert len(notices) == 1
    assert notices[0].title == "Telegram reminder sent"


@pytest.mark.asyncio
async def test_assistant_ask_stays_due(session: AsyncSession):
    user = await _user_with_credits(session)
    task = await _schedule(session, user, "assistant_ask")
    due = task.next_run_at
    result = await process_scheduled_task(session, task, now=NOW)
    assert result.skipped_reason == "unimplemented"
    assert task.next_run_at == due


@pytest.mark.asyncio
async def test_gmail_analyze_recent_uses_readonly_api(monkeypatch: pytest.MonkeyPatch):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen.append(url)
        auth = request.headers.get("authorization", "")
        assert auth == f"Bearer {MOCK_ACCESS}"
        if request.method == "GET" and url.endswith("/messages") or "/messages?" in url:
            if "maxResults=" in url:
                return httpx.Response(200, json={"messages": [{"id": "m1"}]})
        if "/messages/m1" in url:
            return httpx.Response(
                200,
                json={
                    "id": "m1",
                    "snippet": "Please review",
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Invoice due"},
                            {"name": "From", "value": "billing@example.com"},
                        ]
                    },
                },
            )
        return httpx.Response(404, json={"error": "missing"})

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    summary, creds = await GmailService().analyze_recent(
        {"access_token": MOCK_ACCESS, "refresh_token": MOCK_REFRESH},
        query="newer_than:1d",
        max_results=5,
    )
    assert "Invoice due" in summary
    assert creds["access_token"] == MOCK_ACCESS
    assert MOCK_ACCESS not in summary
    assert any("gmail.googleapis.com" in item for item in seen)
    assert all("send" not in item for item in seen)


@pytest.mark.asyncio
async def test_gmail_refreshes_on_unauthorized_then_summarizes(monkeypatch: pytest.MonkeyPatch):
    from urllib.parse import parse_qs

    calls = {"list": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
            assert form.get("grant_type") == "refresh_token"
            assert form.get("refresh_token") == MOCK_REFRESH
            return httpx.Response(200, json={"access_token": "ya29.rotated", "expires_in": 3600})
        if "/messages" in str(request.url) and request.headers.get("authorization") == f"Bearer {MOCK_ACCESS}":
            calls["list"] += 1
            return httpx.Response(401, json={"error": "invalid"})
        if "/messages?" in str(request.url) or str(request.url).endswith("/messages"):
            return httpx.Response(200, json={"messages": []})
        return httpx.Response(404, json={})

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    summary, creds = await GmailService().analyze_recent(
        {"access_token": MOCK_ACCESS, "refresh_token": MOCK_REFRESH},
        query="newer_than:1d",
    )
    assert "No recent messages" in summary
    assert creds["access_token"] == "ya29.rotated"
    assert calls["list"] == 1


@pytest.mark.asyncio
async def test_telegram_send_message_posts_to_bot_api(monkeypatch: pytest.MonkeyPatch):
    import json

    posted: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert MOCK_BOT in str(request.url)
        assert str(request.url).endswith("/sendMessage")
        posted.append(json.loads(request.content.decode()))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    await TelegramService().send_message(MOCK_CHAT, "Scheduled reminder from your assistant.")
    assert posted == [{"chat_id": MOCK_CHAT, "text": "Scheduled reminder from your assistant."}]


def test_mail_summary_omits_empty_mailbox_secrets():
    text = format_mail_summary([])
    assert "No recent messages" in text
    _assert_no_secrets(text)


@pytest.mark.asyncio
async def test_gmail_success_persists_rotated_access_without_plaintext_leak(session: AsyncSession):
    user = await _user_with_credits(session)
    row = await _connect(
        session,
        user,
        "gmail",
        {"access_token": MOCK_ACCESS, "refresh_token": MOCK_REFRESH},
    )
    task = await _schedule(session, user, "gmail_analyze")

    async def analyze(credentials, payload):
        del payload
        updated = dict(credentials)
        updated["access_token"] = "ya29.rotated-access"
        return "1 recent message(s):\n- Hello", updated

    result = await process_scheduled_task(session, task, now=NOW, gmail_analyze=analyze)
    assert result.advanced is True
    reloaded = await session.scalar(
        select(Integration)
        .options(undefer(Integration.encrypted_credentials))
        .where(Integration.id == row.id)
    )
    assert reloaded is not None
    assert "ya29.rotated-access" not in reloaded.encrypted_credentials
    stored = decrypt_json(reloaded.encrypted_credentials)
    assert stored["access_token"] == "ya29.rotated-access"
    assert stored["refresh_token"] == MOCK_REFRESH
