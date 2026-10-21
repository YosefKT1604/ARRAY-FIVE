from datetime import datetime, UTC

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.models.approval import Approval
from app.models.disruption import Disruption
from app.models.recovery_plan import RecoveryPlanRecord
from app.schemas.approval import DecisionRequest
from contracts import Decision, DisruptionStatus, PlanStatus


def next_approval_id(db: Session):
    count = db.scalar(select(func.count()).select_from(Approval))
    return f"AP-{count + 1:03d}"

def record_decision(db: Session, record: RecoveryPlanRecord, reviewer_id: str, decision: Decision, data: DecisionRequest) -> Approval:
    approval = Approval(
        id=next_approval_id(db),
        plan_id=record.id,
        plan_version=data.plan_version,
        reviewer_id=reviewer_id,
        decision=decision,
        comments=data.comments,
        decided_at=datetime.now(UTC),
    )
    if decision == Decision.APPROVED:
        record.status = PlanStatus.APPROVED
        disruption = db.get(Disruption, record.disruption_id)
        disruption.status = DisruptionStatus.DECIDED
    else:
        record.status = PlanStatus.REJECTED
    db.add(approval)
    db.commit()
    return approval