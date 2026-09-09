from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.router import AIRouter
from app.ai.types import GenerateRequest
from app.core.settings import get_settings
from app.models.assistant import AIUsage, AssistantProfile, AssistantTask, TaskCost
from app.models.user import User
from app.services.credits import CreditService, InsufficientCredits


DEFAULT_TASK_COSTS = (
    {
        "task_type": "assistant_ask",
        "base_credit_cost": 5,
        "minimum_cost": 1,
        "maximum_cost": 20,
        "enabled": True,
    },
)


class AssistantUnavailable(Exception):
    pass


class AssistantService:
    def __init__(self, session: AsyncSession, provider) -> None:
        self._session = session
        self._provider = provider
        self._router = AIRouter()
        self._credits = CreditService(session)

    async def ensure_task_costs(self) -> None:
        for row in DEFAULT_TASK_COSTS:
            existing = await self._session.scalar(
                select(TaskCost).where(TaskCost.task_type == row["task_type"])
            )
            if existing is None:
                self._session.add(TaskCost(**row))
        await self._session.flush()

    async def get_or_create_profile(self, user_id: UUID) -> AssistantProfile:
        profile = await self._session.scalar(
            select(AssistantProfile).where(AssistantProfile.user_id == user_id)
        )
        if profile is None:
            profile = AssistantProfile(user_id=user_id)
            self._session.add(profile)
            await self._session.flush()
        return profile

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
        profile = await self.get_or_create_profile(user_id)
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
        await self._session.flush()
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
        await self.ensure_task_costs()
        cost = await self._session.scalar(
            select(TaskCost).where(TaskCost.task_type == task_type, TaskCost.enabled.is_(True))
        )
        if cost is None:
            return 5
        return max(cost.minimum_cost, min(cost.base_credit_cost, cost.maximum_cost))

    async def ask(self, user: User, message: str) -> AssistantTask:
        message = message.strip()
        if not message:
            raise ValueError("Message is required")
        profile = await self.get_or_create_profile(user.id)
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
            f"You are {profile.assistant_name}, a personal assistant. "
            f"Personality: {profile.personality}. "
            f"Response style: {profile.response_style}. "
            f"Language: {profile.language}. "
            "Never mention AI providers, model names, tokens, or routing."
        )
        result = await self._provider.generate(
            GenerateRequest(
                route_key=route.route_key,
                system=system,
                user_message=message,
                timeout_seconds=settings.ai_timeout_seconds,
            )
        )
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
        self._session.add(usage)

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
