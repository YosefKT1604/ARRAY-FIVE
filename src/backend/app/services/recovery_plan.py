from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.disruption import Disruption
from app.models.recovery_plan import RecoveryPlanRecord
from app.services.activity_log import log_activity
from app.services.recovery import generate_plans
from app.services.snapshot import build_snapshot
from contracts import RecoveryPlan, DisruptionStatus, ImpactResult, NormalizedIncident
from contracts.enums import ActivityType

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

def create_recovery_plans(db: Session, disruption: Disruption) -> list[RecoveryPlan]:
    incident = NormalizedIncident.model_validate(disruption.incident)
    impact = ImpactResult.model_validate(disruption.impact)
    # Analysis stores only the impact result, not the snapshot, so it is rebuilt here.
    snapshot = build_snapshot(db, incident)
    count = db.scalar(select(func.count()).select_from(RecoveryPlanRecord))

    plans = []
    for number, plan in enumerate(generate_plans(incident, snapshot, impact), start=count + 1):
        plan = with_new_id(plan, f"RP-{number:03d}")
        db.add(RecoveryPlanRecord(id=plan.id, disruption_id=disruption.id, status=plan.status,
                                  plan=plan.model_dump(mode="json")))
        plans.append(plan)

    disruption.status = DisruptionStatus.PLANS_READY
    log_activity(db, disruption.id, ActivityType.PLANS_GENERATED, details={"plan_ids": [plan.id for plan in plans]})
    db.commit()
    return plans

def list_recovery_plans(db: Session, disruption_id: str) -> list[RecoveryPlan]:
    query = select(RecoveryPlanRecord).where(RecoveryPlanRecord.disruption_id == disruption_id)
    return [to_contract(record) for record in db.scalars(query.order_by(RecoveryPlanRecord.id))]

def get_recovery_plan(db: Session, plan_id: str) -> RecoveryPlanRecord | None:
    return db.get(RecoveryPlanRecord, plan_id)