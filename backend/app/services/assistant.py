from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.router import AIRouter
from app.ai.types import GenerateRequest, GenerateResult
from app.core.settings import get_settings
from app.models.assistant import AIUsage, AssistantProfile, AssistantTask, TaskCost
from app.models.user import User
from app.services.credits import CreditService, InsufficientCredits

log = logging.getLogger("app.assistant")

DEFAULT_ASK_COST = 5
DEFAULT_ASSISTANT_NAME = "Assistant"
DEFAULT_PERSONALITY = "Helpful and concise"
DEFAULT_RESPONSE_STYLE = "clear"
DEFAULT_LANGUAGE = "en"
DEFAULT_TIMEZONE = "UTC"

DEFAULT_TASK_COSTS = (
    {
        "task_type": "assistant_ask",
        "base_credit_cost": DEFAULT_ASK_COST,
        "minimum_cost": 1,
        "maximum_cost": 20,
        "enabled": True,
    },
    {
        "task_type": "gmail_analyze",
        "base_credit_cost": 8,
        "minimum_cost": 2,
        "maximum_cost": 40,
        "enabled": True,
    },
    {
        "task_type": "website_monitor",
        "base_credit_cost": 3,
        "minimum_cost": 1,
        "maximum_cost": 15,
        "enabled": True,
    },
    {
        "task_type": "telegram_notify",
        "base_credit_cost": 1,
        "minimum_cost": 1,
        "maximum_cost": 5,
        "enabled": True,
    },
)


def _unsaved_default_profile(user_id: UUID) -> AssistantProfile:
    """Explicit fields — SQLAlchemy ``default=`` is applied on flush, not construct."""
    return AssistantProfile(
        user_id=user_id,
        assistant_name=DEFAULT_ASSISTANT_NAME,
        personality=DEFAULT_PERSONALITY,
        response_style=DEFAULT_RESPONSE_STYLE,
        timezone=DEFAULT_TIMEZONE,
        language=DEFAULT_LANGUAGE,
    )


def default_task_cost(task_type: str) -> int:
    for row in DEFAULT_TASK_COSTS:
        if row["task_type"] == task_type:
            return int(row["base_credit_cost"])
    return DEFAULT_ASK_COST


async def seed_task_costs(session: AsyncSession) -> None:
    """Idempotent catalog seed. Call from an admin session, never pa_app."""
    for row in DEFAULT_TASK_COSTS:
        existing = await session.scalar(
            select(TaskCost).where(TaskCost.task_type == row["task_type"])
        )
        if existing is None:
            session.add(TaskCost(**row))
    await session.flush()


class AssistantUnavailable(Exception):
    pass


class AssistantService:
    def __init__(self, session: AsyncSession, provider) -> None:
        self._session = session
        self._provider = provider
        self._router = AIRouter()
        self._credits = CreditService(session)

    async def ensure_task_costs(self) -> None:
        """Admin/migrate only. Tenant role (pa_app) has SELECT, not INSERT."""
        await seed_task_costs(self._session)

    async def get_profile(self, user_id: UUID) -> AssistantProfile | None:
        return await self._session.scalar(
            select(AssistantProfile).where(AssistantProfile.user_id == user_id)
        )

    async def get_or_create_profile(self, user_id: UUID) -> AssistantProfile:
        """Read, then INSERT. Callers should use an admin session with app.user_id.

        Tenant (pa_app) INSERT is denied when RLS is on without ``{table}_tenant``.
        A persist failure must not 500 GET /api/me/assistant — return defaults.
        """
        try:
            profile = await self.get_profile(user_id)
        except Exception:
            log.warning("assistant profile read failed user_id=%s", user_id, exc_info=True)
            profile = None
        if profile is not None:
            return profile
        profile = _unsaved_default_profile(user_id)
        try:
            self._session.add(profile)
            await self._session.flush()
        except Exception:
            log.exception(
                "assistant profile persist failed user_id=%s; returning defaults",
                user_id,
            )
            try:
                await self._session.rollback()
            except Exception:
                log.exception("assistant profile session rollback failed")
            return _unsaved_default_profile(user_id)
        return profile

    @staticmethod
    def prompt_bits(profile: AssistantProfile | None) -> tuple[str, str, str, str]:
        if profile is None:
            return (
                DEFAULT_ASSISTANT_NAME,
                DEFAULT_PERSONALITY,
                DEFAULT_RESPONSE_STYLE,
                DEFAULT_LANGUAGE,
            )
        return (
            profile.assistant_name,
            profile.personality,
            profile.response_style,
            profile.language,
        )

    async def update_profile(
        self,
        user_id: UUID,
        *,
        assistant_name: str | None = None,
        personality: str | None = None,
        response_style: str | None = None,
        timezone: str | None = None,
        language: str | None = None,
    ) -> AssistantProfile:
        try:
            profile = await self.get_profile(user_id)
        except Exception:
            log.warning("assistant profile read failed user_id=%s", user_id, exc_info=True)
            profile = None
        creating = profile is None
        if creating:
            profile = _unsaved_default_profile(user_id)
        if assistant_name is not None:
            profile.assistant_name = assistant_name.strip()[:80] or profile.assistant_name
        if personality is not None:
            profile.personality = personality.strip()[:255]
        if response_style is not None:
            profile.response_style = response_style.strip()[:64]
        if timezone is not None:
            profile.timezone = timezone.strip()[:64] or "UTC"
        if language is not None:
            profile.language = language.strip()[:32] or "en"
        snapshot = _unsaved_default_profile(user_id)
        snapshot.assistant_name = profile.assistant_name
        snapshot.personality = profile.personality
        snapshot.response_style = profile.response_style
        snapshot.timezone = profile.timezone
        snapshot.language = profile.language
        try:
            if creating:
                self._session.add(profile)
            await self._session.flush()
        except Exception:
            log.exception(
                "assistant profile persist failed user_id=%s; returning in-memory update",
                user_id,
            )
            try:
                await self._session.rollback()
            except Exception:
                log.exception("assistant profile session rollback failed")
            return snapshot
        return profile

    async def list_tasks(self, user_id: UUID, limit: int = 20) -> list[AssistantTask]:
        result = await self._session.scalars(
            select(AssistantTask)
            .where(AssistantTask.user_id == user_id)
            .order_by(AssistantTask.created_at.desc())
            .limit(limit)
        )
        return list(result.all())

    async def get_task(self, user_id: UUID, task_id: UUID) -> AssistantTask | None:
        task = await self._session.get(AssistantTask, task_id)
        if task is None or task.user_id != user_id:
            return None
        return task

    async def estimate_cost(self, task_type: str) -> int:
        fallback = default_task_cost(task_type)
        try:
            cost = await self._session.scalar(
                select(TaskCost).where(TaskCost.task_type == task_type, TaskCost.enabled.is_(True))
            )
        except Exception:
            log.exception("task_costs read failed for %s; using default %s", task_type, fallback)
            return fallback
        if cost is None:
            return fallback
        return max(cost.minimum_cost, min(cost.base_credit_cost, cost.maximum_cost))

    async def ask(self, user: User, message: str) -> AssistantTask:
        message = message.strip()
        if not message:
            raise ValueError("Message is required")
        try:
            profile = await self.get_profile(user.id)
        except Exception:
            log.warning(
                "assistant profile read failed; using in-memory defaults",
                exc_info=True,
            )
            profile = None
        name, personality, style, language = self.prompt_bits(profile)
        cost = await self.estimate_cost("assistant_ask")
        task = AssistantTask(
            user_id=user.id,
            task_type="assistant_ask",
            status="running",
            input_data=json.dumps({"message": message}),
            credits_reserved=cost,
        )
        self._session.add(task)
        await self._session.flush()
        try:
            await self._credits.reserve(user.id, cost, task_id=task.id)
        except InsufficientCredits:
            task.status = "rejected"
            task.output_data = json.dumps({"error": "insufficient_credits"})
            await self._session.flush()
            raise

        settings = get_settings()
        route = self._router.select(
            task_type="assistant_ask",
            user_plan=user.plan,
            message=message,
        )
        system = (
            f"You are {name}, a personal assistant. "
            f"Personality: {personality}. "
            f"Response style: {style}. "
            f"Language: {language}. "
            "Never mention AI providers, model names, tokens, or routing."
        )
        try:
            result = await self._provider.generate(
                GenerateRequest(
                    route_key=route.route_key,
                    system=system,
                    user_message=message,
                    timeout_seconds=settings.ai_timeout_seconds,
                )
            )
        except Exception:
            log.exception("AI generate failed task_id=%s", task.id)
            result = GenerateResult(text="", success=False, error="unavailable")
        usage = AIUsage(
            user_id=user.id,
            task_id=task.id,
            provider=result.provider,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            actual_cost=0.0,
            credits_charged=cost if result.success else 0,
            latency_ms=result.latency_ms,
            success=result.success,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(usage)
                await self._session.flush()
        except Exception:
            log.exception("ai_usage persist failed task_id=%s", task.id)

        if not result.success:
            await self._credits.release(user.id, cost, task_id=task.id)
            task.status = "failed"
            task.credits_charged = 0
            task.output_data = json.dumps({"error": "unavailable"})
            task.completed_at = datetime.now(timezone.utc)
            await self._session.flush()
            raise AssistantUnavailable()

        await self._credits.settle(user.id, reserved=cost, actual=cost, task_id=task.id)
        task.status = "completed"
        task.credits_charged = cost
        task.output_data = json.dumps({"reply": result.text})
        task.completed_at = datetime.now(timezone.utc)
        await self._session.flush()
        return task
