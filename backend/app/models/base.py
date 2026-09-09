from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase, mapped_column
from sqlalchemy.types import DateTime


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


def timestamp_column():
    return mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
