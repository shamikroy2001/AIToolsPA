from functools import lru_cache

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.dsn import cors_allowlist, parse_cors_origins, to_async_sqlalchemy


class Settings(BaseSettings):
    """Server-side configuration. Never expose secrets to the Next.js bundle."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    cors_origins: str = Field(default="http://localhost:3000")

    database_url: str = Field(
        default="postgresql+asyncpg://pa_app:pa_app@localhost:5432/personal_assistant"
    )
    database_admin_url: str | None = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/personal_assistant"
    )
    public_app_url: str = Field(default="http://localhost:3000")
    redis_url: str = Field(default="redis://localhost:6379/0")

    clerk_secret_key: str | None = None
    clerk_publishable_key: str | None = None
    clerk_issuer: str | None = None
    clerk_jwks_url: str | None = None

    stripe_enabled: bool = Field(default=True)
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_basic_price_id: str | None = None
    stripe_pro_price_id: str | None = None
    stripe_premium_price_id: str | None = None

    ai_gateway_api_key: str | None = None
    ai_gateway_base_url: str | None = None
    ai_route_simple: str | None = None
    ai_route_default: str | None = None
    ai_route_long_context: str | None = None
    ai_retries: int = Field(default=2)
    ai_timeout_seconds: float = Field(default=30.0)

    supabase_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL"),
    )
    supabase_publishable_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SUPABASE_PUBLISHABLE_KEY",
            "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
        ),
    )
    supabase_secret_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SUPABASE_SECRET_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
        ),
    )

    gmail_client_id: str | None = None
    gmail_client_secret: str | None = None

    telegram_bot_token: str | None = None

    credential_encryption_key: str | None = None

    @model_validator(mode="after")
    def _normalize_runtime(self):
        object.__setattr__(self, "database_url", to_async_sqlalchemy(self.database_url))
        if self.database_admin_url:
            object.__setattr__(
                self,
                "database_admin_url",
                to_async_sqlalchemy(self.database_admin_url),
            )
        return self

    def cors_origin_list(self) -> list[str]:
        parsed = parse_cors_origins(self.cors_origins) or ["http://localhost:3000"]
        return cors_allowlist(*parsed, self.public_app_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
