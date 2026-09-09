"""FastAPI application. D1-staging freeze."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401
from app.api.assistant import router as assistant_router
from app.api.billing import router as billing_router
from app.api.health import router as health_router
from app.api.me import router as me_router
from app.api.webhooks import router as webhook_router
from app.core.db import admin_session_factory, get_app_engine, init_engines_from_settings
from app.core.settings import get_settings
from app.models.base import Base
from app.services.plans import PlanService


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_engines_from_settings()
    settings = get_settings()
    engine = get_app_engine()
    if settings.environment == "test" and engine is not None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    elif settings.environment in {"staging", "production"}:
        factory = admin_session_factory()
        async with factory() as session:
            await PlanService(session).ensure_defaults()
            await session.commit()
    yield


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

app.include_router(health_router)
app.include_router(me_router)
app.include_router(billing_router)
app.include_router(webhook_router)
app.include_router(assistant_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "personal-assistant",
        "stage": "D1-staging",
        "docs": "D1 core platform staging freeze. Automations are D2.",
    }
