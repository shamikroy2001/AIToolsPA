from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_tenant_db
from app.models.user import User
from app.schemas.automation import (
    ALLOWED_PROVIDERS,
    IntegrationPublic,
    MonitorCreate,
    MonitorPublic,
    MonitorUpdate,
    NotificationPublic,
    ScheduleCreate,
    SchedulePublic,
    ScheduleUpdate,
)
from app.services.automation import (
    IntegrationService,
    IntegrationUnavailable,
    NotificationService,
    SchedulerService,
    WebsiteMonitorService,
    schedule_public_payload,
)

router = APIRouter(prefix="/api", tags=["automation"])


def _schedule_public(row) -> SchedulePublic:
    return SchedulePublic(
        id=row.id,
        task_type=row.task_type,
        cadence=row.cadence,
        payload=schedule_public_payload(row),
        enabled=row.enabled,
        next_run_at=row.next_run_at,
        created_at=row.created_at,
    )


@router.get("/integrations", response_model=list[IntegrationPublic])
async def list_integrations(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[IntegrationPublic]:
    return await IntegrationService(session).catalog(user.id)


@router.post("/integrations/{provider}/connect", response_model=IntegrationPublic)
async def connect_integration(
    provider: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> IntegrationPublic:
    if provider not in ALLOWED_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown integration")
    try:
        await IntegrationService(session).connect(user.id, provider)
    except IntegrationUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.detail,
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Connection is not available yet.",
    )


@router.post("/integrations/{provider}/disconnect", response_model=IntegrationPublic)
async def disconnect_integration(
    provider: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> IntegrationPublic:
    if provider not in ALLOWED_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown integration")
    return await IntegrationService(session).disconnect(user.id, provider)


@router.get("/monitors", response_model=list[MonitorPublic])
async def list_monitors(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[MonitorPublic]:
    rows = await WebsiteMonitorService(session).list_for(user.id)
    return [MonitorPublic.model_validate(row) for row in rows]


@router.post("/monitors", response_model=MonitorPublic)
async def create_monitor(
    body: MonitorCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> MonitorPublic:
    row = await WebsiteMonitorService(session).create(
        user.id, url=body.url, enabled=body.enabled
    )
    return MonitorPublic.model_validate(row)


@router.get("/monitors/{monitor_id}", response_model=MonitorPublic)
async def read_monitor(
    monitor_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> MonitorPublic:
    row = await WebsiteMonitorService(session).get(user.id, monitor_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    return MonitorPublic.model_validate(row)


@router.patch("/monitors/{monitor_id}", response_model=MonitorPublic)
async def update_monitor(
    monitor_id: UUID,
    body: MonitorUpdate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> MonitorPublic:
    row = await WebsiteMonitorService(session).update(
        user.id, monitor_id, url=body.url, enabled=body.enabled
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    return MonitorPublic.model_validate(row)


@router.delete("/monitors/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monitor(
    monitor_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> Response:
    deleted = await WebsiteMonitorService(session).delete(user.id, monitor_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/schedules", response_model=list[SchedulePublic])
async def list_schedules(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[SchedulePublic]:
    rows = await SchedulerService(session).list_for(user.id)
    return [_schedule_public(row) for row in rows]


@router.post("/schedules", response_model=SchedulePublic)
async def create_schedule(
    body: ScheduleCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> SchedulePublic:
    row = await SchedulerService(session).create(
        user.id,
        task_type=body.task_type,
        cadence=body.cadence,
        payload=body.payload,
        enabled=body.enabled,
        next_run_at=body.next_run_at,
    )
    return _schedule_public(row)


@router.get("/schedules/{schedule_id}", response_model=SchedulePublic)
async def read_schedule(
    schedule_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> SchedulePublic:
    row = await SchedulerService(session).get(user.id, schedule_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return _schedule_public(row)


@router.patch("/schedules/{schedule_id}", response_model=SchedulePublic)
async def update_schedule(
    schedule_id: UUID,
    body: ScheduleUpdate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> SchedulePublic:
    row = await SchedulerService(session).update(
        user.id,
        schedule_id,
        task_type=body.task_type,
        cadence=body.cadence,
        payload=body.payload,
        enabled=body.enabled,
        next_run_at=body.next_run_at,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return _schedule_public(row)


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> Response:
    deleted = await SchedulerService(session).delete(user.id, schedule_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/notifications", response_model=list[NotificationPublic])
async def list_notifications(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[NotificationPublic]:
    rows = await NotificationService(session).list_for(user.id)
    return [NotificationPublic.model_validate(row) for row in rows]
