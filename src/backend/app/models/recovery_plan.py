from typing import Any

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey, JSON

from app.db.database import Base

class RecoveryPlanRecord(Base):
    __tablename__ = "recovery_plans"

    id: Mapped[str] = mapped_column(primary_key=True)
    disruption_id: Mapped[str] = mapped_column(ForeignKey("disruptions.id"))
    status: Mapped[str]
    plan: Mapped[dict[str, Any]] = mapped_column(JSON)
