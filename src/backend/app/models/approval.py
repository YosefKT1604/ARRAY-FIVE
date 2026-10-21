from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("recovery_plans.id"))
    plan_version: Mapped[int]
    reviewer_id: Mapped[str]  # user ID as plain text, so Orbyte user IDs fit later
    decision: Mapped[str]
    comments: Mapped[str]
    decided_at: Mapped[datetime]