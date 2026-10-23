from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import DbSession
from app.schemas.whatsapp import InboxList, IncomingMessageCreate, IncomingMessageOut
from app.services.ai import AIAdapterDep
from app.services.whatsapp import auto_report_enabled, list_inbox, receive_message

# Incoming WhatsApp messages. Today they come from the in-app simulator; the endpoints are channel-neutral,
# so a real channel can post the same shape later.
router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

AutoReportDep = Annotated[bool, Depends(auto_report_enabled)]

# A complete reading is filed as a disruption at once (unless SCDC_WHATSAPP_AUTO_REPORT is off);
# the response says which disruption in `disruption_id`.
@router.post("/messages", status_code=201, response_model=IncomingMessageOut)
def post_message(data: IncomingMessageCreate, db: DbSession, adapter: AIAdapterDep,
                 auto_report: AutoReportDep) -> IncomingMessageOut:
    return receive_message(db, data, adapter, auto_report=auto_report)

@router.get("/inbox", response_model=InboxList)
def get_inbox(db: DbSession) -> InboxList:
    return InboxList(items=list_inbox(db))
