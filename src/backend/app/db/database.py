from datetime import datetime, UTC

from sqlalchemy import create_engine, DateTime, TypeDecorator
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

class UTCDateTime(TypeDecorator):
    """SQLite forgets timezones, so store plain UTC and label it as UTC again when it's read back."""
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None

class Base(DeclarativeBase):
    # Every Mapped[datetime] column in every model uses UTCDateTime automatically.
    type_annotation_map = {datetime: UTCDateTime}