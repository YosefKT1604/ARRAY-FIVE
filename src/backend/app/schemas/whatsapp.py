from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from scdc.ai.schemas import ExtractionResult


class IncomingMessageCreate(BaseModel):
    text: str = Field(min_length=1)
    # What the chat app tells us about the sender; all optional. contact_name is the name the owner saved
    # for the number in their own phone, not the sender's self-chosen profile name.
    from_number: str | None = None
    contact_name: str | None = None
    # A contact reference matched against Supplier.contact_reference, e.g. "whatsapp:maju-rental (synthetic)".
    from_contact: str | None = None


class IncomingMessageOut(BaseModel):
    id: str
    channel: str
    received_at: datetime
    text: str
    from_number: str | None
    contact_name: str | None
    from_contact: str | None
    extraction: ExtractionResult
    # The disruption the message was filed as (or linked to); None = it waits for the owner to check it.
    disruption_id: str | None
    report_outcome: Literal["filed", "duplicate"] | None
    # The fixed acknowledgement the sender gets back; it carries no AI output.
    reply: str


class InboxList(BaseModel):
    items: list[IncomingMessageOut]
