from datetime import datetime
from typing import Any

from app.db.database import Base
from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[str] = mapped_column(primary_key=True)
    disruption_id: Mapped[str] = mapped_column(ForeignKey("disruptions.id"))
    plan_id: Mapped[str | None]
    actor_id: Mapped[str]
    activity_type: Mapped[str]
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime]
