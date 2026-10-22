from datetime import datetime, UTC

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.models.approval import Approval
from app.models.disruption import Disruption
from app.models.recovery_plan import RecoveryPlanRecord
from app.schemas.approval import DecisionRequest
from app.services.activity_log import log_activity
from contracts import Decision, DisruptionStatus, PlanStatus
from contracts.enums import ActivityType

PLAN_STATUS = {
    Decision.APPROVED: PlanStatus.APPROVED,
    Decision.REJECTED: PlanStatus.REJECTED,
    Decision.MORE_INFO_REQUESTED: PlanStatus.MORE_INFO_REQUESTED,
}

ACTIVITY_TYPE = {
    Decision.APPROVED: ActivityType.PLAN_APPROVED,
    Decision.REJECTED: ActivityType.PLAN_REJECTED,
    Decision.MORE_INFO_REQUESTED: ActivityType.INFO_REQUESTED,
}

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
    record.status = PLAN_STATUS[decision]
    if decision == Decision.APPROVED:
        disruption = db.get(Disruption, record.disruption_id)
        disruption.status = DisruptionStatus.DECIDED
    db.add(approval)
    log_activity(db, record.disruption_id, ACTIVITY_TYPE[decision], actor_id=reviewer_id, plan_id=record.id,
                 details={"approval_id": approval.id, "plan_version": data.plan_version})
    db.commit()
    return approval