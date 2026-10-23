from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.disruption import Disruption
from app.models.draft import DraftMessageRecord
from app.models.recovery_plan import RecoveryPlanRecord
from app.services.activity_log import log_activity
from app.services.recovery_plan import list_recovery_plans, to_contract
from app.services.snapshot import build_snapshot
from contracts import ImpactResult, NormalizedIncident
from contracts.enums import ActivityType
from scdc.ai.adapter import ModelAdapter
from scdc.ai.bridge import ai_impact, ai_incident, ai_plans, ai_snapshot
from scdc.ai.config import demo_now, get_adapter
from scdc.ai.drafts import draft_messages
from scdc.ai.explanation import explain
from scdc.ai.extraction import extract_incident
from scdc.ai.schemas import DraftMessage, Explanation, ExtractionResult

# Malaysia has had no daylight saving since 1982, so a fixed offset is exact (and needs no tzdata on Windows).
MALAYSIA = timezone(timedelta(hours=8))

# Read the SCDC_AI_* settings once. Without a model configured this is NoModelAdapter: every AI call
# returns the deterministic template. Tests override the dependency, so they never reach a real model.
@lru_cache
def get_ai_adapter() -> ModelAdapter:
    return get_adapter()

AIAdapterDep = Annotated[ModelAdapter, Depends(get_ai_adapter)]

# When the message counts as received; "tomorrow" and "Friday" are read relative to this day.
# The demo story happens on 20 Oct 2026, so SCDC_DEMO_NOW can pin the clock there; unset = the real time.
def report_time() -> datetime:
    return demo_now() or datetime.now(MALAYSIA)

# Prefills the report form; nothing is stored, so nothing is logged.
def extract(db: Session, message: str, from_contact: str | None, adapter: ModelAdapter) -> ExtractionResult:
    snapshot = ai_snapshot(build_snapshot(db, None))
    return extract_incident(message, snapshot, report_time(), sender=from_contact, adapter=adapter)

# Built fresh on every request so it always matches the current plans (no cache until a live model is used).
def explain_disruption(db: Session, disruption: Disruption, adapter: ModelAdapter) -> Explanation:
    incident = NormalizedIncident.model_validate(disruption.incident)
    impact = ImpactResult.model_validate(disruption.impact)
    plans = list_recovery_plans(db, disruption.id)
    return explain(ai_incident(incident), ai_impact(impact), ai_plans(plans),
                   snapshot=ai_snapshot(build_snapshot(db, incident)), adapter=adapter)

def draft_to_contract(record: DraftMessageRecord) -> DraftMessage:
    return DraftMessage.model_validate({**record.draft, "status": record.status})

def list_drafts(db: Session, plan_id: str) -> list[DraftMessage]:
    query = select(DraftMessageRecord).where(DraftMessageRecord.plan_id == plan_id)
    return [draft_to_contract(record) for record in db.scalars(query.order_by(DraftMessageRecord.id))]

def get_draft(db: Session, draft_id: str) -> DraftMessageRecord | None:
    return db.get(DraftMessageRecord, draft_id)

# Asking twice returns the same drafts, so the owner's approvals are never lost to a regenerated set.
# The caller has already checked that the plan is approved.
def create_drafts(db: Session, record: RecoveryPlanRecord, actor_id: str, adapter: ModelAdapter) -> list[DraftMessage]:
    existing = list_drafts(db, record.id)
    if existing:
        return existing
    disruption = db.get(Disruption, record.disruption_id)
    incident = NormalizedIncident.model_validate(disruption.incident)
    plan = ai_plans([to_contract(record)])[0]
    drafts = draft_messages(plan, ai_incident(incident), ai_snapshot(build_snapshot(db, incident)), adapter=adapter)

    # The AI module numbers each plan's drafts DM-001 upwards; renumber so drafts of different plans never clash.
    count = db.scalar(select(func.count()).select_from(DraftMessageRecord))
    drafts = [draft.model_copy(update={"id": f"DM-{number:03d}"}) for number, draft in enumerate(drafts, start=count + 1)]
    for draft in drafts:
        db.add(DraftMessageRecord(id=draft.id, plan_id=record.id, status=draft.status,
                                  draft=draft.model_dump(mode="json")))
    log_activity(db, record.disruption_id, ActivityType.DRAFT_CREATED, actor_id=actor_id, plan_id=record.id,
                 details={"draft_ids": [draft.id for draft in drafts]})
    db.commit()
    return drafts

# Approved only means the owner is happy with the text; the system never sends anything.
def approve_draft(db: Session, record: DraftMessageRecord, actor_id: str) -> DraftMessage:
    if record.status != "approved":
        record.status = "approved"
        plan = db.get(RecoveryPlanRecord, record.plan_id)
        log_activity(db, plan.disruption_id, ActivityType.DRAFT_APPROVED, actor_id=actor_id, plan_id=plan.id,
                     details={"draft_id": record.id})
        db.commit()
    return draft_to_contract(record)
