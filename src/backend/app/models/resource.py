from datetime import datetime

from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    unit: Mapped[str]
    owned_quantity: Mapped[int]
    on_hand_quantity: Mapped[int]
    on_hand_verified: Mapped[bool]
    verified_at: Mapped[datetime | None]
    reusable: Mapped[bool]