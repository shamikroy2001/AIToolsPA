from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.models.base import Base, aware_timestamp


class AssistantProfile(Base):
    __tablename__ = "assistant_profiles"
    __table_args__ = (UniqueConstraint("user_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    assistant_name: Mapped[str] = mapped_column(String(80), default="Assistant")
    personality: Mapped[str] = mapped_column(String(255), default="Helpful and concise")
    response_style: Mapped[str] = mapped_column(String(64), default="clear")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    language: Mapped[str] = mapped_column(String(32), default="en")
    created_at: Mapped[datetime] = aware_timestamp()
    updated_at: Mapped[datetime] = aware_timestamp(onupdate=True)


class TaskCost(Base):
    __tablename__ = "task_costs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_type: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    base_credit_cost: Mapped[int] = mapped_column(Integer)
    minimum_cost: Mapped[int] = mapped_column(Integer)
    maximum_cost: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(default=True)


class AssistantTask(Base):
    __tablename__ = "assistant_tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(64), default="assistant_ask")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    input_data: Mapped[str] = mapped_column(Text, default="{}")
    output_data: Mapped[str] = mapped_column(Text, default="{}")
    credits_reserved: Mapped[int] = mapped_column(Integer, default=0)
    credits_charged: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = aware_timestamp()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class AIUsage(Base):
    __tablename__ = "ai_usage"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("assistant_tasks.id"))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    actual_cost: Mapped[float] = mapped_column(default=0.0)
    credits_charged: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = aware_timestamp()
