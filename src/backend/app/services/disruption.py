from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.errors import ApiError, ErrorCode
from app.models.delivery import Delivery
from app.models.disruption import Disruption
from app.models.resource import Resource
from app.models.supplier import Supplier
from app.schemas.disruption import DisruptionCreate
from app.services import clock
from app.services.activity_log import log_activity
from app.services.impact import analyze_impact
from app.services.snapshot import build_snapshot
from contracts import NormalizedIncident, DisruptionStatus, ImpactResult, UnresolvedField
from contracts.enums import ActivityType, UnresolvedReason

# Count + 1 only stays unique because disruptions are never deleted.
def next_disruption_id(db: Session) -> str:
    count = db.scalar(select(func.count()).select_from(Disruption))
    return f"D-{count + 1:03d}"

# Fields the impact analysis cannot work without (CONTRACTS §6.1). If any is missing we keep the report
# but mark it needs_clarification instead of guessing a value.
MATERIAL_FIELDS = ["supplier_id", "resource_id", "quantity_affected", "new_arrival_date"]

def missing_material_fields(data: DisruptionCreate) -> list[UnresolvedField]:
    return [
        UnresolvedField(field=field, reason=UnresolvedReason.MISSING)
        for field in MATERIAL_FIELDS
        if getattr(data, field) is None
    ]

# Reports that cannot be true, as (field, plain-words message) pairs, one per field. A field that was not given
# is not checked here: missing material fields are handled as needs_clarification instead.
def validate_report(db: Session, data: DisruptionCreate) -> list[tuple[str, str]]:
    problems: dict[str, str] = {}
    supplier = db.get(Supplier, data.supplier_id) if data.supplier_id else None
    resource = db.get(Resource, data.resource_id) if data.resource_id else None
    delivery = db.get(Delivery, data.delivery_id) if data.delivery_id else None
    if data.supplier_id and supplier is None:
        problems["supplier_id"] = "We don't know that supplier."
    if data.resource_id and resource is None:
        problems["resource_id"] = "We don't know that item."
    if data.delivery_id and delivery is None:
        problems["delivery_id"] = "We don't know that order."
    elif delivery is not None:
        if supplier is not None and delivery.supplier_id != supplier.id:
            problems["delivery_id"] = "This order is not from the supplier you chose."
        elif resource is not None and delivery.resource_id != resource.id:
            problems["delivery_id"] = "This order does not include the item you chose."
        if data.quantity_affected is not None and data.quantity_affected > delivery.quantity:
            unit = f"{resource.unit}s" if resource is not None else "items"
            problems["quantity_affected"] = f"{data.quantity_affected} {unit} is more than the {delivery.quantity} on this delivery."
    if data.original_arrival_date and data.new_arrival_date and data.new_arrival_date < data.original_arrival_date:
        problems["new_arrival_date"] = "The new date cannot be earlier than the date it was due."
    return list(problems.items())

def create_disruption(db: Session, data: DisruptionCreate) -> Disruption:
    unresolved = missing_material_fields(data)
    incident = NormalizedIncident(
        id=next_disruption_id(db),
        reported_at=clock.now(),
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
    # A failed run (e.g. the delivery doesn't exist) found nothing to analyze; storing it would look like
    # "nothing affected". Leave the disruption as it was and tell the user what is wrong instead.
    if impact.analysis_status == "failed":
        problems = [issue["message"] for issue in impact.data_issues if issue.get("severity") == "error"]
        raise ApiError(status_code=422, code=ErrorCode.VALIDATION_ERROR,
                       detail="Impact analysis failed: " + ("; ".join(problems) or "the incident could not be analyzed"))
    disruption.impact = impact.model_dump(mode="json")
    disruption.plan_state = None  # a fresh analysis starts over
    disruption.status = DisruptionStatus.ANALYZED
    log_activity(db, disruption.id, ActivityType.ANALYSIS_COMPLETED, details={"affected_count": len(impact.affected_entities)})
    db.commit()
    return impact

# Once a disruption is decided, a new report about the same delivery is a genuinely new problem.
CLOSED_STATUSES = [DisruptionStatus.CLOSED, DisruptionStatus.DECIDED]

# Same delivery + same new date while still open = someone reported it twice.
def find_open_duplicate(db: Session, data: DisruptionCreate) -> Disruption | None:
    if data.delivery_id is None or data.new_arrival_date is None:
        return None
    query = select(Disruption).where(Disruption.status.not_in(CLOSED_STATUSES))
    # The incident is a JSON column, so the comparison happens here in Python rather than in SQL.
    for disruption in db.scalars(query):
        incident = disruption.incident
        if (incident.get("delivery_id") == data.delivery_id
                and incident.get("new_arrival_date") == data.new_arrival_date.isoformat()):
            return disruption
    return None
