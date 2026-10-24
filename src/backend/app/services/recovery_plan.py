from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.errors import ApiError, ErrorCode
from app.models.disruption import Disruption
from app.models.recovery_plan import RecoveryPlanRecord
from app.schemas.recovery_plan import PlanState
from app.services.activity_log import log_activity
from app.services.recovery import generate_plans, placeholder_applies
from app.services.snapshot import build_snapshot
from contracts import RecoveryPlan, DisruptionStatus, ImpactResult, NormalizedIncident
from contracts.enums import ActivityType, ImpactStatus

# Approvals only update the status column, so it overrides the (older) status stored inside the JSON.
def to_contract(record: RecoveryPlanRecord) -> RecoveryPlan:
    return RecoveryPlan.model_validate({**record.plan, "status": record.status})

# The recovery module always numbers its plans RP-001 upwards; the backend renumbers them
# so plans from different disruptions never clash.
def with_new_id(plan: RecoveryPlan, plan_id: str) -> RecoveryPlan:
    data = plan.model_dump(mode="json")
    data["id"] = plan_id
    if data["validation"] is not None:
        data["validation"]["plan_id"] = plan_id
    return RecoveryPlan.model_validate(data)

# Why this impact gets no plans, or None when plans can be made. An unclear impact is handled by the caller.
def no_plans_state(incident: NormalizedIncident, impact: ImpactResult) -> PlanState | None:
    statuses = {entity.impact_status for entity in impact.affected_entities}
    has_shortfall = bool(impact.resource_shortfalls)
    if ImpactStatus.CONFIRMED not in statuses and not has_shortfall:
        # A potential_risk means "could be hurt, but a fact is uncertain", so it is never an all-clear.
        if ImpactStatus.POTENTIAL_RISK in statuses:
            return PlanState.PLANNING_NOT_AVAILABLE
        return PlanState.NO_RECOVERY_NEEDED
    if not placeholder_applies(incident, impact):
        return PlanState.PLANNING_NOT_AVAILABLE
    return None

def impact_is_unclear(impact: ImpactResult) -> bool:
    return impact.analysis_status != "complete" or any(e.impact_status == ImpactStatus.UNRESOLVED for e in impact.affected_entities)

# Returns the plans (empty when there is nothing to propose) and the reason they are empty, if any.
def create_recovery_plans(db: Session, disruption: Disruption) -> tuple[list[RecoveryPlan], PlanState | None]:
    incident = NormalizedIncident.model_validate(disruption.incident)
    impact = ImpactResult.model_validate(disruption.impact)
    if impact_is_unclear(impact):
        # Remember why before refusing, so the dashboard can show it; the disruption stays "analyzed".
        disruption.plan_state = PlanState.IMPACT_UNCLEAR
        db.commit()
        raise ApiError(status_code=409, code=ErrorCode.INVALID_STATE_TRANSITION,
                       detail="The impact could not be decided; confirm the facts first.")

    state = no_plans_state(incident, impact)
    plans = []
    if state is None:
        # Fresh snapshot rather than the one from analysis: the business data may have changed in between.
        snapshot = build_snapshot(db, incident)
        count = db.scalar(select(func.count()).select_from(RecoveryPlanRecord))
        for number, plan in enumerate(generate_plans(incident, snapshot, impact), start=count + 1):
            plan = with_new_id(plan, f"RP-{number:03d}")
            db.add(RecoveryPlanRecord(id=plan.id, disruption_id=disruption.id, status=plan.status,
                                      plan=plan.model_dump(mode="json")))
            plans.append(plan)

    disruption.plan_state = state
    disruption.status = DisruptionStatus.PLANS_READY
    details = {"plan_ids": [plan.id for plan in plans]}
    if state is not None:
        details["state"] = state
    log_activity(db, disruption.id, ActivityType.PLANS_GENERATED, details=details)
    db.commit()
    return plans, state

def list_recovery_plans(db: Session, disruption_id: str) -> list[RecoveryPlan]:
    query = select(RecoveryPlanRecord).where(RecoveryPlanRecord.disruption_id == disruption_id)
    return [to_contract(record) for record in db.scalars(query.order_by(RecoveryPlanRecord.id))]

def get_recovery_plan(db: Session, plan_id: str) -> RecoveryPlanRecord | None:
    return db.get(RecoveryPlanRecord, plan_id)