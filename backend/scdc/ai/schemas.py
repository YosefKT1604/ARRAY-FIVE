"""Typed data shapes (schemas) used by the AI module.

These are local copies of the shared contracts in docs/CONTRACTS.md v0.1. Person 2 owns the
real ones (they will live in `scdc.contracts`). When that package exists, replace the classes
below with imports from it and keep the same names, so the rest of `scdc.ai` does not change.

Only the shapes needed so far are defined. More are added as each module is built.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

SCHEMA_VERSION = "1.0"


# --- Base classes -------------------------------------------------------------


class InputModel(BaseModel):
    """Base for data we *receive* from other modules: unknown keys are ignored.

    Example: seed.json contains `users`, which the AI module does not need.
    """

    model_config = ConfigDict(extra="ignore")


class OutputModel(BaseModel):
    """Base for data we *produce*: unknown keys are rejected, so typos fail loudly."""

    model_config = ConfigDict(extra="forbid")


# --- Enums (CONTRACTS.md §3) -----------------------------------------------------


class DisruptionType(str, Enum):
    """Kinds of disruption the system understands. The MVP demo uses `supplier_delay`."""

    SUPPLIER_DELAY = "supplier_delay"
    SUPPLIER_SHORTFALL = "supplier_shortfall"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    STAFF_ABSENCE = "staff_absence"


class InputSource(str, Enum):
    """Where an incident came from: the structured form, or a free-text message."""

    FORM = "form"
    MESSAGE = "message"


class EntityType(str, Enum):
    """Kinds of business record that can appear in a dependency."""

    SUPPLIER = "supplier"
    DELIVERY = "delivery"
    RESOURCE = "resource"
    JOB = "job"
    COMMITMENT = "commitment"


class UnresolvedReason(str, Enum):
    """Why a field could not be filled with a verified value."""

    MISSING = "missing"          # the message does not say
    AMBIGUOUS = "ambiguous"      # it could mean more than one thing ("next week")
    UNMATCHED = "unmatched"      # it names something we have no record of
    CONFLICTING = "conflicting"  # the message or records contradict each other
    UNVERIFIED = "unverified"    # a value we could not trace back to the message


# --- Business snapshot (CONTRACTS.md §4) ----------------------------------------


def money_to_str(value: Decimal) -> str:
    """Write a money amount with exactly 2 decimal places, rounding half up ("2.675" → "2.68")."""
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# A Decimal that is written to JSON as a 2-decimal string ("80.00"), as CONTRACTS.md §2 expects.
MoneyAmount = Annotated[Decimal, PlainSerializer(money_to_str, return_type=str, when_used="json")]


class Money(InputModel):
    """A money amount, e.g. RM 4.00.

    `amount` is a Decimal, not a float: Decimal does exact decimal maths, so
    Decimal("4.00") * 20 == Decimal("80.00") and nothing is lost to rounding.
    It accepts "4.00" (as in seed.json) and is written back to JSON as "80.00".
    """

    amount: MoneyAmount
    currency: str = "MYR"


class Business(InputModel):
    """The business the snapshot belongs to."""

    id: str
    name: str
    timezone: str = "Asia/Kuala_Lumpur"
    currency: str = "MYR"


class Supplier(InputModel):
    """A supplier, with the aliases people use for it in messages ("Maju")."""

    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    contact_reference: str | None = None
    reliability_notes: str = ""


class SupplierOffering(InputModel):
    """What one supplier can provide for one resource, and whether that is confirmed."""

    id: str
    supplier_id: str
    resource_id: str
    available_quantity: int | None = None
    lead_time_days: int
    unit_cost: Money | None = None
    availability_confirmed: bool = False
    confirmed_at: datetime | None = None


class Resource(InputModel):
    """A resource such as folding chairs, with aliases used in messages ("kerusi")."""

    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    unit: str = "unit"
    owned_quantity: int = 0
    on_hand_quantity: int = 0
    on_hand_verified: bool = False
    verified_at: datetime | None = None
    reusable: bool = True


class Delivery(InputModel):
    """An inbound order from a supplier (e.g. DL-01: 40 chairs from Maju on 21 Oct)."""

    id: str
    supplier_id: str
    resource_id: str
    quantity: int
    expected_date: date
    status: str


class BusinessJob(InputModel):
    """A job or event the business has committed to."""

    id: str
    name: str
    description: str = ""
    customer_ref: str | None = None
    event_date: date
    deadline: date
    status: str
    priority: str


class Commitment(InputModel):
    """A customer-facing promise that a job fulfils."""

    id: str
    job_id: str
    commitment_type: str
    required_date: date
    reschedulable: bool
    status: str


class Dependency(InputModel):
    """A directed link between two records, e.g. resource R-01 is required by job J-01."""

    id: str
    source_type: EntityType
    source_id: str
    target_type: EntityType
    target_id: str
    dependency_type: str
    required_quantity: int | None = None
    required_by: date | None = None


class BusinessSnapshot(InputModel):
    """The read-only bundle of business records that Person 2 builds for one disruption."""

    schema_version: str = SCHEMA_VERSION
    as_of: datetime | None = None
    business: Business
    suppliers: list[Supplier] = Field(default_factory=list)
    supplier_offerings: list[SupplierOffering] = Field(default_factory=list)
    resources: list[Resource] = Field(default_factory=list)
    deliveries: list[Delivery] = Field(default_factory=list)
    jobs: list[BusinessJob] = Field(default_factory=list)
    commitments: list[Commitment] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    missing_or_stale: list[Any] = Field(default_factory=list)


# --- Incident and extraction (CONTRACTS.md §6.1, §6.2) ---------------------------

IncidentField = Literal[
    "type", "supplier_id", "resource_id", "delivery_id",
    "quantity_affected", "original_arrival_date", "new_arrival_date",
]

# An incident cannot be analyzed until all of these are resolved (CONTRACTS.md §6.1).
MATERIAL_FIELDS: tuple[str, ...] = ("supplier_id", "resource_id", "quantity_affected", "new_arrival_date")


class UnresolvedField(OutputModel):
    """One field we could not verify: why, what the message said, and any suggested values."""

    field: IncidentField
    reason: UnresolvedReason
    raw_value: str | None = None
    candidates: list[str] = Field(default_factory=list)
    note: str = ""


class DraftIncident(OutputModel):
    """An incident before it is confirmed and given an ID. Used to prefill the form.

    Every field may be empty. An empty field must have a matching entry in `unresolved_fields`.
    """

    schema_version: str = SCHEMA_VERSION
    id: str | None = None
    type: DisruptionType | None = None
    source: InputSource = InputSource.MESSAGE
    supplier_id: str | None = None
    resource_id: str | None = None
    delivery_id: str | None = None
    quantity_affected: int | None = Field(default=None, ge=1)
    original_arrival_date: date | None = None
    new_arrival_date: date | None = None
    description: str = ""
    reported_at: datetime | None = None
    unresolved_fields: list[UnresolvedField] = Field(default_factory=list)


class ExtractionResult(OutputModel):
    """What Module A returns: a form prefill, plus everything a human still has to confirm."""

    schema_version: str = SCHEMA_VERSION
    draft_incident: DraftIncident
    field_evidence: dict[str, str] = Field(default_factory=dict)
    unresolved_fields: list[UnresolvedField] = Field(default_factory=list)
    needs_clarification: bool
    clarification_questions: list[str] = Field(default_factory=list)
    generated_by: str  # "template" (deterministic code) or "model:<name>"
    fallback_used: bool
    warnings: list[str] = Field(default_factory=list)
