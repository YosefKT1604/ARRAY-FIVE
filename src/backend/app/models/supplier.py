from datetime import datetime

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    contact_reference: Mapped[str | None]
    reliability_notes: Mapped[str | None]
    offerings: Mapped[list["SupplierOffering"]] = relationship(order_by="SupplierOffering.id")

class SupplierOffering(Base):
    __tablename__ = "supplier_offerings"

    id: Mapped[str] = mapped_column(primary_key=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"))
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"))
    available_quantity: Mapped[int | None]
    lead_time_days: Mapped[int]
    unit_cost: Mapped[dict[str, str] | None] = mapped_column(JSON)
    availability_confirmed: Mapped[bool]
    confirmed_at: Mapped[datetime | None]
