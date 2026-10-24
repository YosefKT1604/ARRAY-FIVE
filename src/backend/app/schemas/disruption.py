from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from contracts import DisruptionType, InputSource, NormalizedIncident
from contracts.enums import DisruptionStatus


class DisruptionCreate(BaseModel):
    type: DisruptionType
    source: InputSource
    supplier_id: str | None = None
    resource_id: str | None = None
    delivery_id: str | None = None
    quantity_affected: int | None = Field(default=None, ge=1)
    original_arrival_date: date | None = None
    new_arrival_date: date | None = None
    description: str
    raw_message: str | None = None
    client_request_id: str | None = None


class DisruptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: DisruptionType
    source: InputSource
    raw_message: str | None
    description: str
    reported_at: datetime
    reported_by: str | None
    status: DisruptionStatus
    incident: NormalizedIncident
    severity: int | None
    plan_state: str | None = None


class DisruptionCreated(BaseModel):
    disruption: DisruptionOut
    incident: NormalizedIncident
    validation_errors: list[dict[str, str]] = []


class DisruptionList(BaseModel):
    items: list[DisruptionOut]