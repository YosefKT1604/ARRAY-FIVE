from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import DbSession
from app.errors import ApiError, ErrorCode
from app.models.disruption import Disruption
from app.models.recovery_plan import RecoveryPlanRecord, RecoveryPlanVersionRecord
from app.schemas.approval import ApprovalOut, DecisionRequest
from app.services.activity_log import log_activity
from app.services.approval import record_decision
from app.services.identity import CurrentUser, CurrentUserDep
from app.services.permissions import can_decide
from app.schemas.recovery_plan import PlanEdit
from app.services.recovery_plan import edit_recovery_plan, get_recovery_plan, revalidate_recovery_plan, to_contract
from contracts import Decision, PlanStatus, RecoveryPlan, ValidationStatus, DisruptionStatus
from contracts.enums import ActivityType

router = APIRouter(prefix="/recovery-plans", tags=["recovery-plans"])

def get_plan_or_404(db: Session, plan_id: str) -> RecoveryPlanRecord:
    record = get_recovery_plan(db, plan_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Recovery plan {plan_id} not found")
    return record

# Shared by approve, reject and request-info. Permission comes first, so staff can't learn anything about the plan.
def check_can_decide(db: Session, record: RecoveryPlanRecord, user: CurrentUser, data: DecisionRequest) -> RecoveryPlan:
    if not can_decide(user):
        log_activity(db, record.disruption_id, ActivityType.APPROVAL_DENIED, actor_id=user.id, plan_id=record.id,
                     details={"role": user.role})
        # Commit before raising: the request fails, but the denied attempt must still show up in the history.
        db.commit()
        raise HTTPException(status_code=403, detail=f"{user.id} ({user.role}) may not approve or reject plans")
    plan = to_contract(record)
    # The owner must be deciding on the version they actually looked at, not one edited since.
    if data.plan_version != plan.version:
        raise ApiError(status_code=409, code=ErrorCode.STALE_PLAN_VERSION, detail=f"Plan {plan.id} is at version {plan.version}, not {data.plan_version}")
    # A plan on hold for more info can still be decided later; approved or rejected plans are final.
    if plan.status not in (PlanStatus.PROPOSED, PlanStatus.MORE_INFO_REQUESTED):
        raise ApiError(status_code=409, code=ErrorCode.INVALID_STATE_TRANSITION, detail=f"Plan {plan.id} is already {plan.status}")
    return plan

@router.get("/{plan_id}", response_model=RecoveryPlan)
def get_recovery_plan_by_id(plan_id: str, db: DbSession) -> RecoveryPlan:
    return to_contract(get_plan_or_404(db, plan_id))

# Read-only look at any version of a plan, e.g. the original (version 1) of an edited plan. The current version comes
# from the plan's own row; older ones from the archive written when the plan was edited.
@router.get("/{plan_id}/versions/{version}", response_model=RecoveryPlan)
def get_recovery_plan_version(plan_id: str, version: int, db: DbSession) -> RecoveryPlan:
    record = get_plan_or_404(db, plan_id)
    if record.plan["version"] == version:
        return to_contract(record)
    archived = db.get(RecoveryPlanVersionRecord, (plan_id, version))
    if archived is None:
        raise HTTPException(status_code=404, detail=f"Recovery plan {plan_id} has no version {version}")
    return RecoveryPlan.model_validate(archived.plan)

@router.put("/{plan_id}", response_model=RecoveryPlan)
def edit_plan(plan_id: str, data: PlanEdit, user: CurrentUserDep, db: DbSession) -> RecoveryPlan:
    record = get_plan_or_404(db, plan_id)
    if not can_decide(user):
        raise HTTPException(status_code=403, detail=f"{user.id} ({user.role}) may not edit plans")
    return edit_recovery_plan(db, record, data.base_version, data.actions, data.assumptions, user.id)

@router.post("/{plan_id}/revalidate", response_model=RecoveryPlan)
def revalidate_plan(plan_id: str, user: CurrentUserDep, db: DbSession) -> RecoveryPlan:
    return revalidate_recovery_plan(db, get_plan_or_404(db, plan_id), user.id)

@router.post("/{plan_id}/approve", status_code=201, response_model=ApprovalOut)
def approve_plan(plan_id: str, data: DecisionRequest, user: CurrentUserDep, db: DbSession) -> ApprovalOut:
    record = get_plan_or_404(db, plan_id)
    plan = check_can_decide(db, record, user, data)
    # One approved plan per disruption, otherwise the business would act twice on the same shortage.
    # Rejecting the leftover plans afterwards is still fine, so this check lives here, not in check_can_decide.
    disruption = db.get(Disruption, record.disruption_id)
    if disruption.status == DisruptionStatus.DECIDED:
        raise ApiError(status_code=409, code=ErrorCode.INVALID_STATE_TRANSITION,
                       detail=f"Disruption {disruption.id} already has an approved plan")
    # needs_confirmation plans may be approved for now (CONTRACTS §10 #2, still waiting on a team decision).
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
    # Asking for "more info" is useless unless it says what's missing.
    if not data.comments.strip():
        raise HTTPException(status_code=422, detail="Say what information is needed in comments")
    approval = record_decision(db, record, user.id, Decision.MORE_INFO_REQUESTED, data)
    return ApprovalOut.model_validate(approval)