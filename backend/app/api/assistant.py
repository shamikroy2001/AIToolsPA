from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import get_ai_provider
from app.api.deps import get_current_user, get_tenant_db
from app.models.assistant import AssistantTask
from app.models.user import User
from app.schemas.assistant import (
    AskRequest,
    AssistantProfilePublic,
    AssistantProfileUpdate,
    TaskPublic,
)
from app.services.assistant import AssistantService, AssistantUnavailable
from app.services.credits import InsufficientCredits

router = APIRouter(prefix="/api", tags=["assistant"])


def _task_public(task: AssistantTask) -> TaskPublic:
    payload_in = json.loads(task.input_data or "{}")
    payload_out = json.loads(task.output_data or "{}")
    return TaskPublic(
        id=task.id,
        task_type=task.task_type,
        status=task.status,
        message=payload_in.get("message"),
        reply=payload_out.get("reply"),
        credits_charged=task.credits_charged,
        created_at=task.created_at,
        completed_at=task.completed_at,
    )


def _service(session: AsyncSession) -> AssistantService:
    return AssistantService(session, get_ai_provider())


@router.get("/me/assistant", response_model=AssistantProfilePublic)
async def read_assistant(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> AssistantProfilePublic:
    profile = await _service(session).get_or_create_profile(user.id)
    return AssistantProfilePublic.model_validate(profile)


@router.patch("/me/assistant", response_model=AssistantProfilePublic)
async def update_assistant(
    body: AssistantProfileUpdate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> AssistantProfilePublic:
    profile = await _service(session).update_profile(
        user.id,
        assistant_name=body.assistant_name,
        personality=body.personality,
        response_style=body.response_style,
        timezone=body.timezone,
        language=body.language,
    )
    return AssistantProfilePublic.model_validate(profile)


@router.post("/tasks", response_model=TaskPublic)
async def create_task(
    body: AskRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> TaskPublic:
    try:
        task = await _service(session).ask(user, body.message)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except InsufficientCredits as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="You've used your assistant credits. Upgrade your plan to continue.",
        ) from exc
    except AssistantUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Your assistant is temporarily unavailable. Try again shortly.",
        ) from exc
    return _task_public(task)


@router.get("/tasks", response_model=list[TaskPublic])
async def list_tasks(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[TaskPublic]:
    tasks = await _service(session).list_tasks(user.id)
    return [_task_public(task) for task in tasks]


@router.get("/tasks/{task_id}", response_model=TaskPublic)
async def read_task(
    task_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> TaskPublic:
    task = await _service(session).get_task(user.id, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return _task_public(task)
