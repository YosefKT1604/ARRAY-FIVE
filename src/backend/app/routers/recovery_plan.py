from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import DbSession
from app.models.recovery_plan import RecoveryPlanRecord
from app.schemas.approval import ApprovalOut, DecisionRequest
from app.services.activity_log import log_activity
from app.services.approval import record_decision
from app.services.identity import CurrentUser, CurrentUserDep
from app.services.permissions import can_decide
from app.services.recovery_plan import get_recovery_plan, to_contract
from app.errors import ApiError, ErrorCode
from contracts import Decision, PlanStatus, RecoveryPlan, ValidationStatus
from contracts.enums import ActivityType

router = APIRouter(prefix="/recovery-plans", tags=["Recovery Plans"])

def get_plan_or_404(db: Session, plan_id: str) -> RecoveryPlanRecord:
    record = get_recovery_plan(db, plan_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Recovery plan {plan_id} not found")
    return record

def check_can_decide(db: Session, record: RecoveryPlanRecord, user: CurrentUser, data: DecisionRequest) -> RecoveryPlan:
    if not can_decide(user):
        log_activity(db,record.disruption_id, ActivityType.APPROVAL_DENIED, actor_id=user.id, plan_id=record.id, details={"role": user.role})
        db.commit()
        raise HTTPException(status_code=403, detail=f"{user.id} ({user.role}) may not approve or reject plans")
    plan = to_contract(record)
    if data.plan_version != plan.version:
        raise ApiError(status_code=409, code=ErrorCode.STALE_PLAN_VERSION, detail=f"Plan {plan.id} is at version {plan.version}, not {data.plan_version}")
    if plan.status not in (PlanStatus.PROPOSED, PlanStatus.MORE_INFO_REQUESTED):
        raise ApiError(status_code=409, code= ErrorCode.INVALID_STATE_TRANSITION, detail=f"Plan {plan.id} is already {plan.status}")
    return plan

@router.get("/{plan_id}", response_model=RecoveryPlan)
def get_recovery_plan_by_id(plan_id: str, db: DbSession) -> RecoveryPlan:
    return to_contract(get_plan_or_404(db, plan_id))

@router.post("/{plan_id}/approve", status_code=201, response_model=ApprovalOut)
def approve_plan(plan_id: str, data: DecisionRequest, user: CurrentUserDep, db: DbSession) -> ApprovalOut:
    record = get_plan_or_404(db, plan_id)
    plan = check_can_decide(db, record, user, data)
    if plan.validation is None or plan.validation.status == ValidationStatus.INFEASIBLE:
        raise ApiError(status_code=409, code=ErrorCode.PLAN_INFEASIBLE, detail=f"Plan {plan_id} is infeasible and cannot be approved")
    approval = record_decision(db, record, user.id, Decision.APPROVED, data)
    return ApprovalOut.model_validate(approval)

@router.post("/{plan_id}/reject", status_code=201, response_model=ApprovalOut)
def reject_plan(plan_id: str, data: DecisionRequest, user: CurrentUserDep, db: DbSession) -> ApprovalOut:
    record = get_plan_or_404(db, plan_id)
    check_can_decide(db, record, user, data)
    approval = record_decision(db, record, user.id, Decision.REJECTED, data)
    return ApprovalOut.model_validate(approval)

@router.post("/{plan_id}/request-info", status_code=201, response_model=ApprovalOut)
def request_info(plan_id: str, data: DecisionRequest, user: CurrentUserDep, db: DbSession) -> ApprovalOut:
    record = get_plan_or_404(db, plan_id)
    check_can_decide(db, record, user, data)
    approval = record_decision(db, record, user.id, Decision.MORE_INFO_REQUESTED, data)
    return ApprovalOut.model_validate(approval)