import re

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.errors import ApiError, ErrorCode
from app.models.disruption import Disruption
from app.models.recovery_plan import RecoveryPlanRecord, RecoveryPlanVersionRecord
from app.schemas.recovery_plan import PlanState
from app.services.activity_log import log_activity
from app.services import recovery
from app.services.snapshot import build_snapshot
from contracts import BusinessSnapshot, RecoveryPlan, PlanStatus, DisruptionStatus, ImpactResult, NormalizedIncident
from contracts.enums import ActivityType, ImpactStatus

# Approvals only update the status column, so it overrides the (older) status stored inside the JSON.
def to_contract(record: RecoveryPlanRecord) -> RecoveryPlan:
    return RecoveryPlan.model_validate({**record.plan, "status": record.status})

# Why this impact gets no plans, or None when plans can be made. An unclear impact is handled by the caller.
def no_plans_state(impact: ImpactResult) -> PlanState | None:
    statuses = {entity.impact_status for entity in impact.affected_entities}
    has_shortfall = bool(impact.resource_shortfalls)
    if ImpactStatus.CONFIRMED not in statuses and not has_shortfall:
        # A potential_risk means "could be hurt, but a fact is uncertain", so it is never an all-clear.
        if ImpactStatus.POTENTIAL_RISK in statuses:
            return PlanState.PLANNING_NOT_AVAILABLE
        return PlanState.NO_RECOVERY_NEEDED
    return None

# The next free plan and action numbers, so new plans never reuse an ID from an earlier disruption.
# Action IDs are counted over every stored version, because an edited plan keeps its older actions' IDs.
def next_numbers(db: Session) -> tuple[int, int]:
    records = [*db.scalars(select(RecoveryPlanRecord)), *db.scalars(select(RecoveryPlanVersionRecord))]
    numbers = [re.fullmatch(r"RA-(\d+)", action["id"]) for record in records for action in record.plan["actions"]]
    actions = [int(match[1]) for match in numbers if match]
    return db.scalar(select(func.count()).select_from(RecoveryPlanRecord)) + 1, max(actions, default=0) + 1

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

    state = no_plans_state(impact)
    plans = []
    details = {}
    if state is None:
        # Fresh snapshot rather than the one from analysis: the business data may have changed in between.
        snapshot = build_snapshot(db, incident)
        plans, warnings, next_steps = recovery.generate_plans(incident, snapshot, impact, *next_numbers(db))
        plans.sort(key=lambda plan: plan.id)  # same order as the list endpoint; `rank` says which is best
        for plan in plans:
            db.add(RecoveryPlanRecord(id=plan.id, disruption_id=disruption.id, status=plan.status,
                                      plan=plan.model_dump(mode="json")))
        if warnings:
            details["warnings"] = warnings
        if not plans:
            state = PlanState.PLANNING_NOT_AVAILABLE
            details["next_steps"] = next_steps

    disruption.plan_state = state
    disruption.status = DisruptionStatus.PLANS_READY
    details["plan_ids"] = [plan.id for plan in plans]
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

def plan_context(db: Session, record: RecoveryPlanRecord) -> tuple[Disruption, NormalizedIncident, ImpactResult, BusinessSnapshot]:
    disruption = db.get(Disruption, record.disruption_id)
    incident = NormalizedIncident.model_validate(disruption.incident)
    return disruption, incident, ImpactResult.model_validate(disruption.impact), build_snapshot(db, incident)

# Only a plan that is still open can change: an approved or rejected plan is a record of what was decided.
def check_plan_is_open(plan: RecoveryPlan, disruption: Disruption) -> None:
    if plan.status not in (PlanStatus.PROPOSED, PlanStatus.MORE_INFO_REQUESTED) or disruption.status == DisruptionStatus.DECIDED:
        raise ApiError(status_code=409, code=ErrorCode.INVALID_STATE_TRANSITION, detail=f"Plan {plan.id} is already {plan.status} and can't be changed")

# Saves a changed plan in its own row and re-ranks the disruption's other open plans around it.
def store_ranking(db: Session, disruption_id: str, plans: list[RecoveryPlan], incident, snapshot, impact) -> None:
    open_plans = [p for p in plans if p.status in (PlanStatus.PROPOSED, PlanStatus.MORE_INFO_REQUESTED)]
    ranks = {p.id: p.rank for p in recovery.rank_plans(open_plans, incident, snapshot, impact)}
    for record in db.scalars(select(RecoveryPlanRecord).where(RecoveryPlanRecord.disruption_id == disruption_id)):
        if record.id in ranks:
            record.plan = {**record.plan, "rank": ranks[record.id]}

def edit_recovery_plan(db: Session, record: RecoveryPlanRecord, base_version: int, actions: list[dict],
                       assumptions: list[str] | None, actor_id: str) -> RecoveryPlan:
    plan = to_contract(record)
    disruption, incident, impact, snapshot = plan_context(db, record)
    check_plan_is_open(plan, disruption)
    old, new = recovery.edit_plan(plan, base_version, actions, assumptions, incident, snapshot, impact)
    db.add(RecoveryPlanVersionRecord(plan_id=old.id, version=old.version, plan=old.model_dump(mode="json")))
    record.status = new.status
    record.plan = new.model_dump(mode="json")
    store_ranking(db, disruption.id, list_recovery_plans(db, disruption.id), incident, snapshot, impact)
    log_activity(db, disruption.id, ActivityType.PLAN_EDITED, actor_id=actor_id, plan_id=record.id,
                 details={"from_version": old.version, "to_version": new.version, "validation": new.validation.status})
    db.commit()
    db.refresh(record)
    return to_contract(record)

def revalidate_recovery_plan(db: Session, record: RecoveryPlanRecord, actor_id: str) -> RecoveryPlan:
    plan = to_contract(record)
    disruption, incident, impact, snapshot = plan_context(db, record)
    check_plan_is_open(plan, disruption)
    checked = recovery.revalidate_plan(plan, incident, snapshot, impact)
    record.plan = checked.model_dump(mode="json")
    store_ranking(db, disruption.id, list_recovery_plans(db, disruption.id), incident, snapshot, impact)
    log_activity(db, disruption.id, ActivityType.PLAN_REVALIDATED, actor_id=actor_id, plan_id=record.id,
                 details={"version": checked.version, "validation": checked.validation.status})
    db.commit()
    db.refresh(record)
    return to_contract(record)
