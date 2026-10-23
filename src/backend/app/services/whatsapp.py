from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.incoming_message import IncomingMessageRecord
from app.schemas.disruption import DisruptionCreate
from app.schemas.whatsapp import IncomingMessageCreate, IncomingMessageOut
from app.services.activity_log import log_activity
from app.services.ai import report_time
from app.services.disruption import MATERIAL_FIELDS, analyze_disruption, create_disruption, find_open_duplicate
from app.services.snapshot import build_snapshot
from contracts.enums import ActivityType
from scdc.ai.adapter import ModelAdapter
from scdc.ai.bridge import ai_snapshot
from scdc.ai.config import setting
from scdc.ai.extraction import extract_from_message
from scdc.ai.schemas import ExtractionResult, IncomingMessage

# Every channel answers the sender with the same fixed text: the owner has not checked the extraction yet.
ACKNOWLEDGEMENT = "Thanks, your message was received. The owner will confirm."

# Only the simulator exists today; a real channel (Meta Cloud API, OpenWA) would convert its webhook into
# the same IncomingMessageCreate and call receive_message with its own channel name.
SIMULATOR = "simulator"

# SCDC_WHATSAPP_AUTO_REPORT (default on): file a complete reading as a disruption without the owner's click.
# Read on every request, so it can be switched off during a demo without restarting the backend.
def auto_report_enabled() -> bool:
    return (setting("SCDC_WHATSAPP_AUTO_REPORT") or "true").lower() not in ("false", "0", "no", "off")

def next_message_id(db: Session) -> str:
    count = db.scalar(select(func.count()).select_from(IncomingMessageRecord))
    return f"WA-{count + 1:03d}"

def to_contract(record: IncomingMessageRecord) -> IncomingMessageOut:
    return IncomingMessageOut(id=record.id, channel=record.channel, received_at=record.received_at, text=record.text,
                              from_number=record.from_number, contact_name=record.contact_name,
                              from_contact=record.from_contact,
                              extraction=ExtractionResult.model_validate(record.extraction),
                              disruption_id=record.disruption_id, report_outcome=record.report_outcome,
                              reply=ACKNOWLEDGEMENT)

# The report a complete reading stands for, or None if anything is missing or flagged: then the owner checks it.
# Material fields only count when filled and not doubted, so a value shown only as a suggestion never files.
def report_from(extraction: ExtractionResult, text: str) -> DisruptionCreate | None:
    draft = extraction.draft_incident
    if extraction.needs_clarification or extraction.unresolved_fields or draft.type is None:
        return None
    if any(getattr(draft, field) is None for field in MATERIAL_FIELDS):
        return None
    return DisruptionCreate(type=draft.type, source="message", supplier_id=draft.supplier_id,
                            resource_id=draft.resource_id, delivery_id=draft.delivery_id,
                            quantity_affected=draft.quantity_affected,
                            original_arrival_date=draft.original_arrival_date,
                            new_arrival_date=draft.new_arrival_date,
                            description=draft.description or "Reported on WhatsApp", raw_message=text)

# File the report like the form would (P2's create_disruption, then the impact check), or link the message to
# the open disruption that already covers the same delivery and new date. The log says no person filed it.
def file_report(db: Session, record: IncomingMessageRecord, report: DisruptionCreate) -> None:
    details = {"message_id": record.id, "channel": record.channel, "filed_automatically": True}
    duplicate = find_open_duplicate(db, report)
    if duplicate is not None:
        record.disruption_id, record.report_outcome = duplicate.id, "duplicate"
        log_activity(db, duplicate.id, ActivityType.DISRUPTION_EXTRACTED, details={**details, "duplicate": True})
        db.commit()
        return
    disruption = create_disruption(db, report)
    record.disruption_id, record.report_outcome = disruption.id, "filed"
    log_activity(db, disruption.id, ActivityType.DISRUPTION_EXTRACTED, details=details)
    db.commit()
    try:
        analyze_disruption(db, disruption)
    except ApiError:
        pass  # The impact page offers "Check impact" again, exactly as after a form report whose analysis failed.

# Read the message once, on arrival, and keep the reading: the inbox shows it without asking the model again.
# With auto-report on, a complete reading becomes a disruption at once; anything else waits for the owner.
def receive_message(db: Session, data: IncomingMessageCreate, adapter: ModelAdapter, *, auto_report: bool,
                    channel: str = SIMULATOR) -> IncomingMessageOut:
    incoming = IncomingMessage(text=data.text, received_at=report_time(), from_number=data.from_number,
                               contact_name=data.contact_name, from_contact=data.from_contact, channel=channel)
    extraction = extract_from_message(incoming, ai_snapshot(build_snapshot(db, None)), adapter=adapter)
    record = IncomingMessageRecord(id=next_message_id(db), channel=channel, received_at=incoming.received_at,
                                   text=incoming.text, from_number=incoming.from_number,
                                   contact_name=incoming.contact_name, from_contact=incoming.from_contact,
                                   extraction=extraction.model_dump(mode="json"))
    db.add(record)
    db.commit()
    report = report_from(extraction, incoming.text) if auto_report else None
    if report is not None:
        file_report(db, record, report)
    return to_contract(record)

# Newest first, like a chat app's inbox.
def list_inbox(db: Session) -> list[IncomingMessageOut]:
    query = select(IncomingMessageRecord).order_by(IncomingMessageRecord.id.desc())
    return [to_contract(record) for record in db.scalars(query)]
