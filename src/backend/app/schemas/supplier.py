from datetime import datetime

from pydantic import ConfigDict, BaseModel

from app.schemas.money import Money


class SupplierOfferingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    supplier_id: str
    resource_id: str
    available_quantity: int | None
    lead_time_days: int
    unit_cost: Money | None
    availability_confirmed: bool
    confirmed_at: datetime | None

class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    aliases: list[str]
    contact_reference: str | None
    reliability_notes: str | None
    offerings: list[SupplierOfferingOut]

class SupplierList(BaseModel):
    items: list[SupplierOut]
