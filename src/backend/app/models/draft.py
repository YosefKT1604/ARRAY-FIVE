from typing import Any

from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

# A message drafted by the AI module (CONTRACTS §6.7). Never sent: approving it only marks it approved.
class DraftMessageRecord(Base):
    __tablename__ = "draft_messages"

    id: Mapped[str] = mapped_column(primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("recovery_plans.id"))
    status: Mapped[str]
    draft: Mapped[dict[str, Any]] = mapped_column(JSON)
