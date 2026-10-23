from pydantic import BaseModel

from scdc.ai.schemas import DraftMessage


class ExtractRequest(BaseModel):
    message: str
    # The sender as the chat app reports it, matched against Supplier.contact_reference
    # (e.g. "whatsapp:maju-rental (synthetic)"). The demo message never names the supplier.
    from_contact: str | None = None


class DraftMessageList(BaseModel):
    items: list[DraftMessage]
