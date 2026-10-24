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


# The recovery_plans row always holds the NEWEST version of a plan, so approvals (which point at the plan ID and
# check plan_version) keep working unchanged. Older versions are archived here, as "superseded", when a plan is edited.
class RecoveryPlanVersionRecord(Base):
    __tablename__ = "recovery_plan_versions"

    plan_id: Mapped[str] = mapped_column(ForeignKey("recovery_plans.id"), primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    plan: Mapped[dict[str, Any]] = mapped_column(JSON)
