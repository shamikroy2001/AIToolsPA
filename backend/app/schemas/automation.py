from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


ALLOWED_PROVIDERS = frozenset({"gmail", "telegram"})
ALLOWED_SCHEDULE_TYPES = frozenset(
    {"assistant_ask", "website_monitor", "gmail_analyze", "telegram_notify"}
)
ALLOWED_CADENCES = frozenset({"hourly", "daily", "weekly"})
FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "credential",
        "credentials",
        "encrypted_credentials",
        "api_key",
        "bot_token",
        "client_secret",
    }
)


class IntegrationPublic(BaseModel):
    provider: str
    name: str
    description: str
    status: str


class MonitorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=8, max_length=2048)
    enabled: bool = True

    @field_validator("url")
    @classmethod
    def http_url(cls, value: str) -> str:
        url = value.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return url


class MonitorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str | None = Field(default=None, min_length=8, max_length=2048)
    enabled: bool | None = None

    @field_validator("url")
    @classmethod
    def http_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        url = value.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return url


class MonitorPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    enabled: bool
    last_checked_at: datetime | None
    last_changed_at: datetime | None
    created_at: datetime


class ScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: str = Field(min_length=1, max_length=64)
    cadence: str = Field(default="daily", max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    next_run_at: datetime | None = None

    @field_validator("task_type")
    @classmethod
    def known_task_type(cls, value: str) -> str:
        task_type = value.strip()
        if task_type not in ALLOWED_SCHEDULE_TYPES:
            raise ValueError("Unsupported schedule type")
        return task_type

    @field_validator("cadence")
    @classmethod
    def known_cadence(cls, value: str) -> str:
        cadence = value.strip().lower()
        if cadence not in ALLOWED_CADENCES:
            raise ValueError("Cadence must be hourly, daily, or weekly")
        return cadence

    @field_validator("payload")
    @classmethod
    def no_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        lowered = {str(key).lower() for key in value}
        if lowered & FORBIDDEN_PAYLOAD_KEYS:
            raise ValueError("Payload must not include credentials")
        return value


class ScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: str | None = Field(default=None, min_length=1, max_length=64)
    cadence: str | None = Field(default=None, max_length=64)
    payload: dict[str, Any] | None = None
    enabled: bool | None = None
    next_run_at: datetime | None = None

    @field_validator("task_type")
    @classmethod
    def known_task_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        task_type = value.strip()
        if task_type not in ALLOWED_SCHEDULE_TYPES:
            raise ValueError("Unsupported schedule type")
        return task_type

    @field_validator("cadence")
    @classmethod
    def known_cadence(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cadence = value.strip().lower()
        if cadence not in ALLOWED_CADENCES:
            raise ValueError("Cadence must be hourly, daily, or weekly")
        return cadence

    @field_validator("payload")
    @classmethod
    def no_secrets(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return value
        lowered = {str(key).lower() for key in value}
        if lowered & FORBIDDEN_PAYLOAD_KEYS:
            raise ValueError("Payload must not include credentials")
        return value


class SchedulePublic(BaseModel):
    id: UUID
    task_type: str
    cadence: str
    payload: dict[str, Any]
    enabled: bool
    next_run_at: datetime | None
    created_at: datetime


class NotificationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel: str
    title: str
    body: str
    read_at: datetime | None
    created_at: datetime
