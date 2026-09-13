from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, aware_timestamp


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    monthly_credits: Mapped[int] = mapped_column(Integer)
    rollover_cap: Mapped[int] = mapped_column(Integer)
    rollover_expiry_days: Mapped[int] = mapped_column(Integer, default=90)
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="usd")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = aware_timestamp()
    updated_at: Mapped[datetime] = aware_timestamp(onupdate=True)
