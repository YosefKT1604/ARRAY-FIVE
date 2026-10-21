from datetime import date, datetime
from typing import Any, Literal

from contracts.base import ContractModel, Money, Quantity
from contracts.enums import DeliveryStatus, DependencyType, EntityType, Priority

# Business records (CONTRACTS.md §4). The API returns the them.

class Business(ContractModel):
    id: str
    name: str
    timezone: str
    currency: str

class Supplier(ContractModel):
    id: str
    name: str
    aliases: list[str]
    contact_reference: str | None
    reliability_notes: str | None

class SupplierOffering(ContractModel):
    id: str
    supplier_id: str
    resource_id: str
    available_quantity: Quantity | None
    lead_time_days: int
    unit_cost: Money | None
    availability_confirmed: bool
    confirmed_at: datetime | None

class Resource(ContractModel):
    id: str
    name: str
    aliases: list[str]
    unit: str
    owned_quantity: Quantity
    on_hand_quantity: Quantity
    on_hand_verified: bool
    verified_at: datetime | None
    reusable: bool

class Delivery(ContractModel):
    id: str
    supplier_id: str
    resource_id: str
    quantity: Quantity
    expected_date: date
    status: DeliveryStatus

class Job(ContractModel):
    id: str
    name: str
    description: str | None
    customer_ref: str | None
    event_date: date
    deadline: date
    status: str
    priority: Priority

class Commitment(ContractModel):
    id: str
    job_id: str
    commitment_type: str
    required_date: date
    reschedulable: bool
    status: str

class Dependency(ContractModel):
    id: str
    source_type: EntityType
    source_id: str
    target_type: EntityType
    target_id: str
    dependency_type: DependencyType
    required_quantity: Quantity | None
    required_by: date | None

class BusinessSnapshot(ContractModel):
    """Read-only bundle the backend builds for one disruption and hands to impact, recovery and AI."""
    schema_version: Literal["1.0"] = "1.0"
    as_of: datetime
    business: Business
    suppliers: list[Supplier]
    supplier_offerings: list[SupplierOffering]
    resources: list[Resource]
    deliveries: list[Delivery]
    jobs: list[Job]
    commitments: list[Commitment]
    dependencies: list[Dependency]
    missing_or_stale: list[dict[str, Any]] = []