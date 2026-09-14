from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, aware_timestamp


class StripeEvent(Base):
    __tablename__ = "stripe_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(128))
    payload: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = aware_timestamp()
