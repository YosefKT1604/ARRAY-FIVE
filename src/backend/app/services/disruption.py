from datetime import datetime, UTC

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.models.disruption import Disruption
from app.schemas.disruption import DisruptionCreate
from app.services.activity_log import log_activity
from app.services.impact import analyze_impact
from app.services.snapshot import build_snapshot
from contracts import NormalizedIncident, DisruptionStatus, ImpactResult, UnresolvedField
from contracts.enums import ActivityType, UnresolvedReason

def next_disruption_id(db: Session) -> str:
    count = db.scalar(select(func.count()).select_from(Disruption))
    return f"D-{count + 1:03d}"

# Fields the impact analysis cannot work without
MATERIAL_FIELDS = ["supplier_id", "resource_id", "quantity_affected", "new_arrival_date"]

def missing_material_fields(data: DisruptionCreate) -> list[UnresolvedField]:
    return [
        UnresolvedField(field=field, reason=UnresolvedReason.MISSING)
        for field in MATERIAL_FIELDS
        if getattr(data, field) is None
    ]

def create_disruption(db: Session, data: DisruptionCreate) -> Disruption:
    unresolved = missing_material_fields(data)
    incident = NormalizedIncident(
        id=next_disruption_id(db),
        reported_at=datetime.now(UTC),
        unresolved_fields=unresolved,
        **data.model_dump(exclude={"raw_message", "client_request_id"}),
    )
    disruption = Disruption(
        id=incident.id,
        type=incident.type,
        source=incident.source,
        raw_message=data.raw_message,
        description=incident.description,
        reported_at=incident.reported_at,
        reported_by=None,
        status=DisruptionStatus.NEEDS_CLARIFICATION if unresolved else DisruptionStatus.RECEIVED,
        incident=incident.model_dump(mode="json"),
        severity=None,
    )
    db.add(disruption)
    log_activity(db, disruption_id=disruption.id, activity_type=ActivityType.DISRUPTION_REPORTED, details={"type": incident.type})
    db.commit()
    return disruption

def list_disruptions(db: Session) -> list[Disruption]:
    return list(db.scalars(select(Disruption).order_by(Disruption.id)))


def get_disruption(db: Session, disruption_id: str) -> Disruption | None:
    return db.get(Disruption, disruption_id)

def analyze_disruption(db: Session, disruption: Disruption) -> ImpactResult:
    incident = NormalizedIncident.model_validate(disruption.incident)
    impact = analyze_impact(incident, build_snapshot(db, incident))
    disruption.impact = impact.model_dump(mode="json")
    disruption.status = DisruptionStatus.ANALYZED
    log_activity(db, disruption.id, ActivityType.ANALYSIS_COMPLETED, details={"affected_count": len(impact.affected_entities)})
    db.commit()
    return impact

CLOSED_STATUSES = [DisruptionStatus.CLOSED, DisruptionStatus.DECIDED]

def find_open_duplicate(db: Session, data: DisruptionCreate) -> Disruption | None:
    if data.delivery_id is None or data.new_arrival_date is None:
        return None
    query = select(Disruption).where(Disruption.status.not_in(CLOSED_STATUSES))
    for disruption in db.scalars(query):
        incident = disruption.incident
        if (incident.get("delivery_id") == data.delivery_id
                and incident.get("new_arrival_date") == data.new_arrival_date.isoformat()):
            return disruption
    return None
