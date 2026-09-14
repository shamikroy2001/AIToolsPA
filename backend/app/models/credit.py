from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, aware_timestamp

SOURCE_MONTHLY = "monthly"
SOURCE_ROLLOVER = "rollover"
SOURCE_TOPUP = "topup"

TX_MONTHLY_ALLOCATION = "MONTHLY_ALLOCATION"
TX_ROLLOVER = "ROLLOVER"
TX_AI_USAGE = "AI_USAGE"
TX_TOPUP = "TOPUP"
TX_REFUND = "REFUND"
TX_ADMIN_ADJUSTMENT = "ADMIN_ADJUSTMENT"
TX_EXPIRATION = "EXPIRATION"
TX_RESERVATION = "RESERVATION"
TX_RELEASE = "RELEASE"


class CreditAccount(Base):
    __tablename__ = "credit_accounts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    monthly_allowance: Mapped[int] = mapped_column(Integer, default=0)
    rollover_cap: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = aware_timestamp()
    updated_at: Mapped[datetime] = aware_timestamp(onupdate=True)


class CreditLot(Base):
    __tablename__ = "credit_lots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    original_amount: Mapped[int] = mapped_column(Integer)
    remaining_amount: Mapped[int] = mapped_column(Integer)
    billing_period: Mapped[str | None] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    extra: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = aware_timestamp()


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    credit_lot_id: Mapped[UUID | None] = mapped_column(ForeignKey("credit_lots.id"))
    transaction_type: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    task_id: Mapped[UUID | None] = mapped_column()
    description: Mapped[str] = mapped_column(String(255), default="")
    stripe_event_id: Mapped[str | None] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = aware_timestamp()
