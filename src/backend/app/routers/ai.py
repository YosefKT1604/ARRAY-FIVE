from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from app.dependencies import DbSession
from app.errors import ApiError, ErrorCode
from app.routers.disruption import get_disruption_or_404
from app.routers.recovery_plan import get_plan_or_404
from app.schemas.ai import DraftMessageList, ExtractRequest
from app.services.ai import AIAdapterDep, approve_draft, create_drafts, explain_disruption, extract, get_draft
from app.services.identity import CurrentUserDep
from app.services.permissions import can_decide
from contracts import PlanStatus
from scdc.ai.schemas import DraftMessage, Explanation, ExtractionResult

# The AI module's endpoints (CONTRACTS §7). Every one works without a model: it falls back to templates.
router = APIRouter(tags=["ai"])

# Only prefills the report form; the owner still confirms it through POST /disruptions.
@router.post("/disruptions/extract", response_model=ExtractionResult)
def extract_disruption(data: ExtractRequest, db: DbSession, adapter: AIAdapterDep) -> ExtractionResult:
    return extract(db, data.message, data.from_contact, adapter)

@router.get("/disruptions/{disruption_id}/explanation", response_model=Explanation)
def get_explanation(disruption_id: str, db: DbSession, adapter: AIAdapterDep) -> Explanation:
    disruption = get_disruption_or_404(db, disruption_id)
    if disruption.impact is None:
        raise ApiError(status_code=409, code=ErrorCode.INVALID_STATE_TRANSITION,
                       detail=f"Disruption {disruption_id} has not been analyzed yet")
    return explain_disruption(db, disruption, adapter)

# Anyone may ask for drafts (they are only text); approving one is the owner's call.
@router.post("/recovery-plans/{plan_id}/drafts", status_code=201, response_model=DraftMessageList)
def generate_drafts(plan_id: str, db: DbSession, adapter: AIAdapterDep,
                    x_user_id: Annotated[str | None, Header()] = None) -> DraftMessageList:
    record = get_plan_or_404(db, plan_id)
    if record.status != PlanStatus.APPROVED:
        raise ApiError(status_code=409, code=ErrorCode.INVALID_STATE_TRANSITION,
                       detail=f"Drafts can only be made for an approved plan; {plan_id} is {record.status}")
    return DraftMessageList(items=create_drafts(db, record, x_user_id or "system", adapter))

@router.post("/drafts/{draft_id}/approve", response_model=DraftMessage)
def approve_draft_message(draft_id: str, user: CurrentUserDep, db: DbSession) -> DraftMessage:
    record = get_draft(db, draft_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")
    if not can_decide(user):
        raise HTTPException(status_code=403, detail=f"{user.id} ({user.role}) may not approve drafts")
    return approve_draft(db, record, user.id)
