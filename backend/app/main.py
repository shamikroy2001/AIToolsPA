"""FastAPI application. D1-staging freeze."""

from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

import app.models  # noqa: F401
from app.api.assistant import router as assistant_router
from app.api.automation import router as automation_router
from app.api.billing import router as billing_router
from app.api.health import router as health_router
from app.api.me import router as me_router
from app.api.webhooks import router as webhook_router
from app.core.db import admin_session_factory, get_app_engine, init_engines_from_settings
from app.core.settings import get_settings
from app.models.base import Base
from app.services.assistant import seed_task_costs
from app.services.plans import PlanService

log = logging.getLogger("app.main")


async def seed_plan_catalog() -> None:
    from app.core.schema import ensure_core_schema, missing_relation

    last_error: Exception | None = None
    recovered = False
    try:
        await ensure_core_schema()
        recovered = True
    except Exception:
        log.exception("asyncpg schema ensure failed")
    for attempt in range(12):
        try:
            factory = admin_session_factory()
            async with factory() as session:
                await PlanService(session).ensure_defaults()
                await seed_task_costs(session)
                await session.commit()
            return
        except Exception as exc:
            last_error = exc
            log.warning("Plan seed attempt %s failed: %s", attempt + 1, exc)
            if not recovered and missing_relation(exc):
                try:
                    await ensure_core_schema()
                    recovered = True
                    continue
                except Exception:
                    log.exception("asyncpg schema create failed")
            await asyncio.sleep(2)
    log.exception("Plan seed failed; serving /health without catalog seed", exc_info=last_error)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        init_engines_from_settings()
    except Exception:
        log.exception("Database engine init failed; serving /health")
    settings = get_settings()
    engine = get_app_engine()
    seed_task: asyncio.Task | None = None
    if settings.environment == "test" and engine is not None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    elif settings.environment in {"staging", "production"}:
        # Must not await DB here: Starlette blocks listening until lifespan yields.
        seed_task = asyncio.create_task(seed_plan_catalog())
    yield
    if seed_task is not None:
        seed_task.cancel()
        try:
            await seed_task
        except (asyncio.CancelledError, Exception):
            pass


class Log5xxMiddleware:
    """Pure ASGI — BaseHTTPMiddleware re-raises handled exceptions and hides CORS."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start" and message.get("status", 0) >= 500:
                log.error(
                    "HTTP %s on %s %s",
                    message.get("status"),
                    scope.get("method"),
                    scope.get("path"),
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)


settings = get_settings()

app = FastAPI(
    title="Personal Assistant API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.add_middleware(Log5xxMiddleware)


def _cors_error_headers(request: Request) -> dict[str, str]:
    """ServerErrorMiddleware sits outside CORSMiddleware; attach ACAO here."""
    origin = (request.headers.get("origin") or "").rstrip("/")
    if origin and origin in settings.cors_origin_list():
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        }
    return {}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # FastAPI wires Exception/500 handlers onto ServerErrorMiddleware (outermost).
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong. Try again shortly."},
        headers=_cors_error_headers(request),
    )

app.include_router(health_router)
app.include_router(me_router)
app.include_router(billing_router)
app.include_router(webhook_router)
app.include_router(assistant_router)
app.include_router(automation_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "personal-assistant",
        "stage": "D1-staging",
        "docs": "D1 core platform staging freeze. Automations are D2.",
    }
