from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AssistantProfilePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assistant_name: str
    personality: str
    response_style: str
    timezone: str
    language: str


class AssistantProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assistant_name: str | None = Field(default=None, max_length=80)
    personality: str | None = Field(default=None, max_length=255)
    response_style: str | None = Field(default=None, max_length=64)
    timezone: str | None = Field(default=None, max_length=64)
    language: str | None = Field(default=None, max_length=32)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=8000)


class TaskPublic(BaseModel):
    id: UUID
    task_type: str
    status: str
    message: str | None = None
    reply: str | None = None
    credits_charged: int
    created_at: datetime
    completed_at: datetime | None = None
