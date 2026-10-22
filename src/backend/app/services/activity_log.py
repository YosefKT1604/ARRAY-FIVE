from datetime import datetime, UTC
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from contracts.enums import ActivityType


def next_activity_id(db: Session) -> str:
    count = db.scalar(select(func.count()).select_from(ActivityLog))
    return f"LOG-{count + 1:04d}"

def log_activity(db: Session, disruption_id: str, activity_type: ActivityType, actor_id: str = "system",
                 plan_id: str | None = None, details: dict[str, Any] | None = None) -> None:
    db.add(ActivityLog(
        id=next_activity_id(db),
        disruption_id=disruption_id,
        plan_id=plan_id,
        actor_id=actor_id,
        activity_type=activity_type,
        details=details or {},
        created_at=datetime.now(UTC),
    ))

def list_activity(db: Session, disruption_id: str) -> list[ActivityLog]:
    query = select(ActivityLog).where(ActivityLog.disruption_id == disruption_id)
    return list(db.scalars(query.order_by(ActivityLog.created_at, ActivityLog.id)))