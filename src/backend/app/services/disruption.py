from datetime import datetime, UTC

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.models.disruption import Disruption
from app.schemas.disruption import DisruptionCreate
from app.services.impact import analyze_impact
from contracts import NormalizedIncident, DisruptionStatus, ImpactResult


def next_disruption_id(db: Session) -> str:
    count = db.scalar(select(func.count()).select_from(Disruption))
    return f"D-{count + 1:03d}"


def create_disruption(db: Session, data: DisruptionCreate) -> Disruption:
    incident = NormalizedIncident(
        id=next_disruption_id(db),
        reported_at=datetime.now(UTC),
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
        status=DisruptionStatus.RECEIVED,
        incident=incident.model_dump(mode="json"),
        severity=None,
    )
    db.add(disruption)
    db.commit()
    return disruption


def list_disruptions(db: Session) -> list[Disruption]:
    return list(db.scalars(select(Disruption).order_by(Disruption.id)))


def get_disruption(db: Session, disruption_id: str) -> Disruption | None:
    return db.get(Disruption, disruption_id)

def analyze_disruption(db: Session, disruption: Disruption) -> ImpactResult:
    impact = analyze_impact(NormalizedIncident.model_validate(disruption.incident))
    disruption.impact = impact.model_dump(mode="json")
    disruption.status = DisruptionStatus.ANALYZED
    db.commit()
    return impact

