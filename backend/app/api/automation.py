from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_tenant_db
from app.core.db import admin_session_factory, apply_tenant
from app.core.settings import get_settings
from app.models.user import User
from app.schemas.automation import (
    ALLOWED_PROVIDERS,
    FORBIDDEN_PAYLOAD_KEYS,
    IntegrationConnectBody,
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
    IntegrationBadRequest,
    IntegrationService,
    IntegrationUnavailable,
    NotificationService,
    SchedulerService,
    WebsiteMonitorService,
    schedule_public_payload,
)
from app.services.gmail import GmailOAuthError, decode_oauth_state, gmail_redirect_uri

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


def _integration_http_error(exc: IntegrationUnavailable | IntegrationBadRequest) -> HTTPException:
    code = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if isinstance(exc, IntegrationUnavailable)
        else status.HTTP_400_BAD_REQUEST
    )
    return HTTPException(status_code=code, detail=exc.detail)


def _frontend_integrations(query: str) -> str:
    return f"{get_settings().public_app_url.rstrip('/')}/integrations?{query}"


async def _connect_body(request: Request) -> IntegrationConnectBody:
    """Parse connect JSON without echoing tokens if a secret key is posted."""
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        return IntegrationConnectBody()
    try:
        raw = await request.json()
    except Exception:
        return IntegrationConnectBody()
    if raw in (None, ""):
        return IntegrationConnectBody()
    if not isinstance(raw, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid connect payload")
    lowered = {str(key).lower() for key in raw}
    if lowered & FORBIDDEN_PAYLOAD_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request must not include credentials",
        )
    try:
        return IntegrationConnectBody.model_validate(raw)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid connect payload") from None


@router.post("/integrations/{provider}/connect", response_model=IntegrationPublic)
async def connect_integration(
    provider: str,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> IntegrationPublic:
    if provider not in ALLOWED_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown integration")
    payload = await _connect_body(request)
    try:
        return await IntegrationService(session).connect(
            user.id,
            provider,
            redirect_uri=gmail_redirect_uri(request),
            code=payload.code,
            state=payload.state,
            chat_id=payload.chat_id,
        )
    except (IntegrationUnavailable, IntegrationBadRequest) as exc:
        raise _integration_http_error(exc) from exc


@router.get("/integrations/gmail/callback")
async def gmail_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Google OAuth redirect. Anonymous; user is bound by the signed state."""
    if error or not code or not state:
        return RedirectResponse(_frontend_integrations("gmail=error"), status_code=302)
    try:
        user_id = decode_oauth_state(state)
    except (GmailOAuthError, IntegrationUnavailable) as exc:
        del exc
        return RedirectResponse(_frontend_integrations("gmail=error"), status_code=302)
    factory = admin_session_factory()
    try:
        async with factory() as session:
            await apply_tenant(session, user_id)
            await IntegrationService(session).complete_gmail(
                user_id,
                code=code,
                state=state,
                redirect_uri=gmail_redirect_uri(request),
            )
            await session.commit()
    except (IntegrationUnavailable, IntegrationBadRequest, GmailOAuthError):
        return RedirectResponse(_frontend_integrations("gmail=error"), status_code=302)
    return RedirectResponse(_frontend_integrations("gmail=connected"), status_code=302)


@router.post("/integrations/{provider}/disconnect", response_model=IntegrationPublic)
async def disconnect_integration(
    provider: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> IntegrationPublic:
    if provider not in ALLOWED_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown integration")
    try:
        return await IntegrationService(session).disconnect(user.id, provider)
    except (IntegrationUnavailable, IntegrationBadRequest) as exc:
        raise _integration_http_error(exc) from exc


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
