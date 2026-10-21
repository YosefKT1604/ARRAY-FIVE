from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from contracts.base import ContractModel
from contracts.enums import DisruptionType, InputSource, UnresolvedReason


class UnresolvedField(ContractModel):
    field: str
    reason: UnresolvedReason
    raw_value: Any = None
    candidates: list[str] = []
    note: str | None = None

class NormalizedIncident(ContractModel):
    """A disruption in structured form (section 6.1). Unknown values are null and listed in unresolved_fields."""
    schema_version: Literal["1.0"] = "1.0"
    id: str | None = None
    type: DisruptionType
    source: InputSource
    supplier_id: str | None
    resource_id: str | None
    delivery_id: str | None
    quantity_affected: int | None = Field(ge=1)
    original_arrival_date: date | None
    new_arrival_date: date | None
    description: str
    reported_at: datetime
    unresolved_fields: list[UnresolvedField] = []