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


class ImpactStatus(str, Enum):
    """How sure Person 3's impact analysis is that a record is affected."""

    CONFIRMED = "confirmed"
    POTENTIAL_RISK = "potential_risk"
    UNRESOLVED = "unresolved"


class ValidationStatus(str, Enum):
    """Person 4's verdict on a plan. Only P4 sets it; the AI module only copies it."""

    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    NEEDS_CONFIRMATION = "needs_confirmation"


class CheckResult(str, Enum):
    """The outcome of one validation check on a plan."""

    PASS = "pass"
    FAIL = "fail"
    UNRESOLVED = "unresolved"


class CheckCode(str, Enum):
    """Which rule a validation check tested."""

    RESOURCE_AVAILABLE = "RESOURCE_AVAILABLE"
    QUANTITY_SUFFICIENT = "QUANTITY_SUFFICIENT"
    SUPPLIER_AVAILABLE = "SUPPLIER_AVAILABLE"
    LEAD_TIME_OK = "LEAD_TIME_OK"
    DEADLINE_MET = "DEADLINE_MET"
    NO_DOUBLE_BOOKING = "NO_DOUBLE_BOOKING"
    DEPENDENCY_ORDER_OK = "DEPENDENCY_ORDER_OK"
    COMMITMENT_RESCHEDULABLE = "COMMITMENT_RESCHEDULABLE"
    FACTS_KNOWN = "FACTS_KNOWN"


class PlanStatus(str, Enum):
    """Where a recovery plan is in the owner's decision process."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    MORE_INFO_REQUESTED = "more_info_requested"
    SUPERSEDED = "superseded"


class ActionType(str, Enum):
    """Kinds of step a recovery plan can contain."""

    USE_SPARE_INVENTORY = "use_spare_inventory"
    SOURCE_ALTERNATIVE_SUPPLIER = "source_alternative_supplier"
    REALLOCATE_RESOURCE = "reallocate_resource"
    RESCHEDULE_JOB = "reschedule_job"
    SPLIT_ALLOCATION = "split_allocation"
    CONTACT_SUPPLIER = "contact_supplier"


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
    phone: str | None = None  # not in CONTRACTS yet (ask P2); any format, compared after normalising
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


class IncomingMessage(InputModel):
    """A message as it arrives (e.g. on WhatsApp), with what the channel tells us about the sender.

    `contact_name` is the name the business owner saved for the sender's number in their own contacts
    (e.g. "Ali Maju Rental"), not the sender's self-chosen profile name.
    """

    text: str
    received_at: datetime                 # becomes the report time
    from_number: str | None = None        # the sender's phone, any format ("+60 12-345 6789", "012-3456789")
    contact_name: str | None = None       # the owner's saved name for that number
    from_contact: str | None = None       # a contact reference, e.g. "whatsapp:maju-rental (synthetic)"
    channel: str = "whatsapp"


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


class RawFlag(OutputModel):
    """A field the extractor (model or rules) is itself unsure about."""

    field: IncidentField
    reason: Literal["ambiguous", "conflicting", "missing"]
    note: str = ""
    candidates: list[str] = Field(default_factory=list)  # suggestions, e.g. ["20", "30"]


class RawExtraction(OutputModel):
    """What the extraction model must return, and what the rule-based extractor produces.

    Names are as written in the message ("Maju", "chairs"); code maps them to IDs.
    Dates and quantity are final values. Nothing here is trusted until step 2d checks it.
    """

    disruption_type: DisruptionType | None = None
    supplier_name: str | None = None
    resource_name: str | None = None
    quantity_affected: int | None = Field(default=None, ge=1)
    original_arrival_date: date | None = None
    new_arrival_date: date | None = None
    flags: list[RawFlag] = Field(default_factory=list)


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


class NormalizedIncident(InputModel):
    """A confirmed incident (CONTRACTS.md §6.1), as Person 2 passes it to Modules B and C."""

    schema_version: str = SCHEMA_VERSION
    id: str | None = None
    type: DisruptionType
    source: InputSource
    supplier_id: str | None = None
    resource_id: str | None = None
    delivery_id: str | None = None
    quantity_affected: int | None = Field(default=None, ge=1)
    original_arrival_date: date | None = None
    new_arrival_date: date | None = None
    description: str
    reported_at: datetime
    unresolved_fields: list[UnresolvedField] = Field(default_factory=list)


# --- Impact and recovery plans (CONTRACTS.md §6.3–6.5; Persons 3 and 4) -----------


class Evidence(InputModel):
    """A fact about a record that supports an impact finding."""

    entity_id: str
    fact: str


class AffectedEntity(InputModel):
    """One record the disruption affects, with why and through which dependencies."""

    entity_type: EntityType
    entity_id: str
    impact_status: ImpactStatus
    severity: int = Field(ge=0, le=10)
    reason: str
    dependency_path: list[str]
    evidence: list[Evidence] = Field(default_factory=list)


class CheckedNotAffected(InputModel):
    """A record that was checked and found not affected."""

    entity_type: EntityType
    entity_id: str
    reason: str


class ResourceShortfall(InputModel):
    """How many units of a resource are missing on a given date."""

    resource_id: str
    date: date
    required: int = Field(ge=0)
    available: int = Field(ge=0)
    shortfall: int = Field(ge=0)


class ImpactResult(InputModel):
    """Person 3's impact analysis for one disruption."""

    schema_version: str = SCHEMA_VERSION
    disruption_id: str
    affected_entities: list[AffectedEntity]
    checked_not_affected: list[CheckedNotAffected] = Field(default_factory=list)
    resource_shortfalls: list[ResourceShortfall] = Field(default_factory=list)
    unresolved_facts: list[dict[str, Any]] = Field(default_factory=list)


class EntityRef(InputModel):
    """A pointer to a business record."""

    entity_type: EntityType
    entity_id: str


class RecoveryAction(InputModel):
    """One step of a recovery plan; `parameters` depend on `action_type` (CONTRACTS.md §6.4)."""

    id: str
    action_type: ActionType
    target_entity: EntityRef
    parameters: dict[str, Any]
    status: str


class Check(InputModel):
    """One deterministic validation check on a plan."""

    code: CheckCode
    result: CheckResult
    detail: str
    evidence_ids: list[str] = Field(default_factory=list)


class ValidationResult(InputModel):
    """Person 4's validation of one plan version. Its status is the only source of truth."""

    plan_id: str
    plan_version: int
    status: ValidationStatus
    checks: list[Check]
    unresolved_assumptions: list[str] = Field(default_factory=list)
    validated_at: datetime | None = None


class RecoveryPlan(InputModel):
    """A candidate recovery plan from Person 4, with its validation."""

    schema_version: str = SCHEMA_VERSION
    id: str
    disruption_id: str
    version: int = Field(ge=1)
    summary: str
    actions: list[RecoveryAction]
    assumptions: list[str] = Field(default_factory=list)
    estimated_cost: Money | None = None
    validation: ValidationResult | None = None
    rank: int | None = None
    status: PlanStatus
    created_by: str


# --- Explanation (CONTRACTS.md §6.6; Module B) -----------------------------------------


class ImpactExplanation(OutputModel):
    """Plain-language text about one affected record."""

    entity_id: str
    text: str


class PlanComparison(OutputModel):
    """One plan's benefits and limitations. `validation_status` is copied from P4, never generated."""

    plan_id: str
    validation_status: ValidationStatus | None  # None only if P4 has not validated the plan yet
    benefits: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class Explanation(OutputModel):
    """What Module B returns. The UI labels it AI-generated when `generated_by` starts with "model:"."""

    schema_version: str = SCHEMA_VERSION
    disruption_id: str
    summary: str
    impact_explanations: list[ImpactExplanation] = Field(default_factory=list)
    plan_comparisons: list[PlanComparison] = Field(default_factory=list)
    missing_confirmations: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    generated_by: str
    fallback_used: bool
    unsupported_claims_removed: int = 0


class RawItem(OutputModel):
    """One benefit or limitation written by the model, keyed to what it explains.

    `source` is a check code (e.g. "DEADLINE_MET"), "assumption:N" (the plan's Nth assumption,
    from 1) or "cost". Code checks that every key exists for that plan and none is missing.
    """

    source: str
    text: str = Field(min_length=1)


class RawPlanComparison(OutputModel):
    """The model's benefits and limitations for one plan (no status: code copies it)."""

    plan_id: str
    benefits: list[RawItem] = Field(default_factory=list)
    limitations: list[RawItem] = Field(default_factory=list)


class RecipientType(str, Enum):
    """Who a draft message is for."""

    SUPPLIER = "supplier"
    CUSTOMER = "customer"


class DraftMessage(OutputModel):
    """A message for the owner to review (CONTRACTS.md §6.7). It is never sent by the system.

    `placeholders` lists the gaps in `body` the owner must fill in, without brackets ("DELIVERY_ADDRESS").
    """

    id: str
    plan_id: str
    recipient_type: RecipientType
    recipient_id: str | None
    body: str
    placeholders: list[str] = Field(default_factory=list)
    status: Literal["draft", "approved"] = "draft"
    generated_by: str


class RawDraft(OutputModel):
    """What the drafting model must return: the polished message text only."""

    body: str = Field(min_length=1)


class RawExplanation(OutputModel):
    """What the explanation model must return. Nothing here is trusted until the claim check."""

    summary: str = Field(min_length=1)
    impact_explanations: list[ImpactExplanation] = Field(default_factory=list)
    plan_comparisons: list[RawPlanComparison] = Field(default_factory=list)
