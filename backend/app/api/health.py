from fastapi import APIRouter

from app.core.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "personal-assistant-api",
        "environment": settings.environment,
        "release": "D1-staging",
        "billing": "dormant" if not settings.stripe_enabled else "stripe",
    }


@router.get("/api/health")
async def api_health() -> dict[str, str]:
    return await health()
