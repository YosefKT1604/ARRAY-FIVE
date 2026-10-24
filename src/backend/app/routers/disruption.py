from fastapi import APIRouter, HTTPException, Response
from sqlalchemy.orm import Session

from app.dependencies import DbSession
from app.errors import ApiError, ErrorCode
from app.models.disruption import Disruption
from app.schemas.activity_log import ActivityLogList
from app.schemas.disruption import DisruptionCreate, DisruptionCreated, DisruptionOut, DisruptionList
from app.schemas.recovery_plan import RecoveryPlanList
from app.services.activity_log import list_activity
from app.services.disruption import (
    analyze_disruption, create_disruption, find_open_duplicate, get_disruption, list_disruptions,
    validate_report,
)
from app.services.recovery_plan import create_recovery_plans, list_recovery_plans
from contracts import DisruptionStatus, ImpactResult

router = APIRouter(prefix="/disruptions", tags=["disruptions"])

def get_disruption_or_404(db: Session, disruption_id: str) -> Disruption:
    disruption = get_disruption(db, disruption_id)
    if disruption is None:
        raise HTTPException(status_code=404, detail=f"Disruption {disruption_id} not found")
    return disruption

@router.post("", status_code=201, response_model=DisruptionCreated)
def report_disruption(data: DisruptionCreate, db: DbSession) -> DisruptionCreated:
    problems = validate_report(db, data)
    if problems:
        raise ApiError(status_code=422, code=ErrorCode.VALIDATION_ERROR, detail="Some details need fixing.",
                       errors=[{"loc": ["body", field], "msg": message, "type": "value_error"} for field, message in problems])
    duplicate = find_open_duplicate(db, data)
    if duplicate is not None:
        raise ApiError(status_code=409, code=ErrorCode.DUPLICATE_DISRUPTION,
                       detail=f"Disruption {duplicate.id} is already open for delivery {data.delivery_id} "
                              f"arriving {data.new_arrival_date}")
    disruption = create_disruption(db, data)
    return DisruptionCreated(disruption=disruption, incident=disruption.incident)

@router.get("", response_model=DisruptionList)
def get_disruptions(db: DbSession) -> DisruptionList:
    return DisruptionList(items=list_disruptions(db))

@router.get("/{disruption_id}", response_model=DisruptionOut)
def get_disruption_by_id(db: DbSession, disruption_id: str) -> DisruptionOut:
    return DisruptionOut.model_validate(get_disruption_or_404(db, disruption_id))

@router.post("/{disruption_id}/analyze", response_model=ImpactResult)
def analyze(db: DbSession, disruption_id: str) -> ImpactResult:
    disruption = get_disruption_or_404(db, disruption_id)
    if disruption.status == DisruptionStatus.NEEDS_CLARIFICATION:
        raise ApiError(status_code=409, code=ErrorCode.INVALID_STATE_TRANSITION, detail="Disruption needs clarification before it can be analyzed")
    # Re-analysing after plans exist would reopen a finished disruption and allow a second batch of plans.
    if disruption.status not in (DisruptionStatus.RECEIVED, DisruptionStatus.ANALYZED):
        raise ApiError(status_code=409, code=ErrorCode.INVALID_STATE_TRANSITION,
                       detail=f"Disruption {disruption_id} is already {disruption.status}")
    return analyze_disruption(db, disruption)

@router.get("/{disruption_id}/impact", response_model=ImpactResult)
def get_impact(disruption_id: str, db: DbSession) -> ImpactResult:
    disruption = get_disruption_or_404(db, disruption_id)
    if disruption.impact is None:
        raise HTTPException(status_code=404, detail=f"Disruption {disruption_id} has not been analyzed yet")
    return ImpactResult.model_validate(disruption.impact)

@router.post("/{disruption_id}/recovery-plans", status_code=201, response_model=RecoveryPlanList)
def generate_recovery_plans(disruption_id: str, db: DbSession, response: Response) -> RecoveryPlanList:
    disruption = get_disruption_or_404(db, disruption_id)
    if disruption.status != DisruptionStatus.ANALYZED:
        raise ApiError(status_code=409, code=ErrorCode.INVALID_STATE_TRANSITION, detail=f"Plans need an analyzed disruption; {disruption_id} is {disruption.status}")
    plans, state = create_recovery_plans(db, disruption)
    # Nothing was created when there is nothing to propose, so that is a plain 200 rather than a 201.
    if not plans:
        response.status_code = 200
    return RecoveryPlanList(items=plans, state=state)

@router.get("/{disruption_id}/recovery-plans", response_model=RecoveryPlanList)
def get_recovery_plans(disruption_id: str, db: DbSession) -> RecoveryPlanList:
    disruption = get_disruption_or_404(db, disruption_id)
    return RecoveryPlanList(items=list_recovery_plans(db, disruption_id), state=disruption.plan_state)

@router.get("/{disruption_id}/activity-log", response_model=ActivityLogList)
def get_activity_log(disruption_id: str, db: DbSession) -> ActivityLogList:
    get_disruption_or_404(db, disruption_id)
    return ActivityLogList(items=list_activity(db, disruption_id))