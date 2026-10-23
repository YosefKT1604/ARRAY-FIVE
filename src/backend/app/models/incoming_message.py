from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

# A WhatsApp message as it arrived (today from the in-app simulator; later from a real channel),
# with the AI module's reading of it. A complete reading is filed as a disruption straight away;
# anything else waits in the inbox until the owner checks it and reports it through the form.
class IncomingMessageRecord(Base):
    __tablename__ = "incoming_messages"

    id: Mapped[str] = mapped_column(primary_key=True)
    channel: Mapped[str]
    received_at: Mapped[datetime]
    text: Mapped[str]
    from_number: Mapped[str | None]
    contact_name: Mapped[str | None]
    from_contact: Mapped[str | None]
    extraction: Mapped[dict[str, Any]] = mapped_column(JSON)
    # Set when the message was filed automatically: "filed" (a new disruption) or "duplicate" (that delivery
    # and new date were already reported, so the message was linked to the open disruption instead).
    disruption_id: Mapped[str | None] = mapped_column(ForeignKey("disruptions.id"))
    report_outcome: Mapped[str | None]
