from datetime import datetime
from typing import Any

from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

class Disruption(Base):
    __tablename__ = "disruptions"

    id: Mapped[str] = mapped_column(primary_key=True)
    type: Mapped[str]
    source: Mapped[str]
    raw_message: Mapped[str | None]
    description: Mapped[str]
    reported_at: Mapped[datetime]
    reported_by: Mapped[str | None]
    status: Mapped[str]
    incident: Mapped[dict[str, Any]] = mapped_column(JSON)
    severity: Mapped[int | None]
    impact: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Why no recovery plans exist for an analyzed disruption (see PlanState); None when plans were made normally.
    plan_state: Mapped[str | None]
