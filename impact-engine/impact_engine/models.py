"""Typed models following SCDC CONTRACTS v0.1 (sections 3, 4, 6.1, 6.3).

INPUT : NormalizedIncident + BusinessSnapshot
OUTPUT: ImpactResult

The input models below are *local mirrors* of the shared contract so this module
runs on its own. At integration, Person 2's `scdc.contracts` models replace them
(same field names); the algorithm only reads the attributes listed here.

The output follows the contract exactly. Fields marked "extension" are additive
extras (not in contract v0.1); `ImpactResult.to_contract()` strips them.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from .config import SeverityConfig


# --------------------------------------------------------------------------- #
# Enums (CONTRACTS section 3)
# --------------------------------------------------------------------------- #
class DisruptionType(str, Enum):
    SUPPLIER_DELAY = "supplier_delay"
    SUPPLIER_SHORTFALL = "supplier_shortfall"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    STAFF_ABSENCE = "staff_absence"


class EntityType(str, Enum):
    SUPPLIER = "supplier"
    DELIVERY = "delivery"
    RESOURCE = "resource"
    JOB = "job"
    COMMITMENT = "commitment"


class DependencyType(str, Enum):
    SHIPS = "ships"        # supplier -> delivery
    SUPPLIES = "supplies"  # delivery -> resource
    REQUIRES = "requires"  # resource -> job   (required_quantity + required_by)
    FULFILS = "fulfils"    # job      -> commitment


class ImpactStatus(str, Enum):
    CONFIRMED = "confirmed"          # recorded numbers prove a shortfall
    POTENTIAL_RISK = "potential_risk"  # could be hurt, but a fact is uncertain
    UNRESOLVED = "unresolved"        # cannot decide: data missing or contradictory


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class UnresolvedReason(str, Enum):
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"
    CONFLICTING = "conflicting"
    UNVERIFIED = "unverified"


# --- not in the contract: how the engine reports its own run (extension) ----- #
class AnalysisStatus(str, Enum):
    COMPLETE = "complete"  # clean data, nothing unresolved
    PARTIAL = "partial"    # ran, but records rejected / warnings / facts missing
    FAILED = "failed"      # incident unusable; no analysis performed


class IssueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class IssueCode(str, Enum):
    INVALID_RECORD = "invalid_record"
    INVALID_INCIDENT = "invalid_incident"
    UNSUPPORTED_INCIDENT_TYPE = "unsupported_incident_type"
    DUPLICATE_ID = "duplicate_id"
    DANGLING_REFERENCE = "dangling_reference"
    INVALID_DEPENDENCY = "invalid_dependency"
    DUPLICATE_DEPENDENCY = "duplicate_dependency"
    CONFLICTING_DEPENDENCY = "conflicting_dependency"
    CONFLICTING_DATA = "conflicting_data"
    DATE_CONFLICT = "date_conflict"
    UNKNOWN_ENTITY = "unknown_entity"
    DERIVED_EDGE = "derived_edge"
    STALE_OR_MISSING = "stale_or_missing"
    PATHS_TRUNCATED = "paths_truncated"
    CYCLE_DETECTED = "cycle_detected"


class DataIssue(BaseModel):
    code: IssueCode
    severity: IssueSeverity
    message: str
    entity_id: Optional[str] = None


# --------------------------------------------------------------------------- #
# Input records (CONTRACTS section 4). Unknown fields are ignored.
# --------------------------------------------------------------------------- #
class Supplier(BaseModel):
    id: str = Field(min_length=1)
    name: str = ""


class Resource(BaseModel):
    id: str = Field(min_length=1)
    name: str = ""
    unit: str = "unit"
    owned_quantity: Optional[int] = Field(default=None, ge=0)
    on_hand_quantity: Optional[int] = Field(default=None, ge=0)  # None = not recorded
    on_hand_verified: bool = False   # conservative default
    reusable: bool = True


class Delivery(BaseModel):
    id: str = Field(min_length=1)
    supplier_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    quantity: int = Field(ge=0)
    expected_date: date
    status: str = "scheduled"  # scheduled | delayed | partially_delivered | delivered | cancelled


class Job(BaseModel):
    id: str = Field(min_length=1)
    name: str = ""
    event_date: date
    deadline: Optional[date] = None
    status: str = "scheduled"
    priority: Priority = Priority.MEDIUM


class Commitment(BaseModel):
    id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    commitment_type: str = ""
    required_date: Optional[date] = None
    reschedulable: Optional[bool] = None
    status: str = "active"


class Dependency(BaseModel):
    id: str = Field(min_length=1)
    source_type: EntityType
    source_id: str = Field(min_length=1)
    target_type: EntityType
    target_id: str = Field(min_length=1)
    dependency_type: DependencyType
    required_quantity: Optional[int] = Field(default=None, ge=0)
    required_by: Optional[date] = None


class BusinessSnapshot(BaseModel):
    schema_version: str = "1.0"
    as_of: Optional[datetime] = None
    suppliers: list[Supplier] = Field(default_factory=list)
    resources: list[Resource] = Field(default_factory=list)
    deliveries: list[Delivery] = Field(default_factory=list)
    jobs: list[Job] = Field(default_factory=list)
    commitments: list[Commitment] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    missing_or_stale: list[Any] = Field(default_factory=list)
    # Problems already found while loading raw records (see loader.py).
    issues: list[DataIssue] = Field(default_factory=list)


class NormalizedIncident(BaseModel):
    """CONTRACTS 6.1."""

    schema_version: str = "1.0"
    id: str = Field(min_length=1)
    type: DisruptionType = DisruptionType.SUPPLIER_DELAY
    source: Optional[str] = None
    supplier_id: Optional[str] = None
    resource_id: Optional[str] = None
    delivery_id: Optional[str] = None
    quantity_affected: Optional[int] = Field(default=None, ge=0)
    original_arrival_date: Optional[date] = None
    new_arrival_date: Optional[date] = None
    description: str = ""
    reported_at: Optional[datetime] = None
    # items: {"field","reason","raw_value","candidates","note"}  (plain strings accepted too)
    unresolved_fields: list[Any] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Output (CONTRACTS 6.3 + extensions)
# --------------------------------------------------------------------------- #
class Evidence(BaseModel):
    entity_id: str
    fact: str


class SeverityBreakdown(BaseModel):  # extension
    deadline_urgency: float       # 0..1
    resource_shortfall: float     # 0..1
    commitment_importance: float  # 0..1
    weights: dict[str, float]
    score: float                  # 0..10, one decimal (severity is this, rounded)
    assumed_factors: list[str] = Field(default_factory=list)


class AffectedEntity(BaseModel):
    entity_type: EntityType
    entity_id: str
    impact_status: ImpactStatus
    severity: Optional[int] = Field(default=None, ge=0, le=10)  # None only when unresolved
    reason: str
    dependency_path: list[str]
    evidence: list[Evidence] = Field(default_factory=list)
    # ---- extensions ----
    priority: Optional[Priority] = None            # band of the score; None when unresolved
    severity_breakdown: Optional[SeverityBreakdown] = None
    dependency_paths: list[list[str]] = Field(default_factory=list)  # ALL routes
    missing_information: list[str] = Field(default_factory=list)


class CheckedNotAffected(BaseModel):
    entity_type: EntityType
    entity_id: str
    reason: str
    dependency_paths: list[list[str]] = Field(default_factory=list)  # extension


class ResourceShortfall(BaseModel):
    resource_id: str
    date: date
    required: int
    available: int
    shortfall: int


class UnresolvedFact(BaseModel):
    """Shape proposed for contract v1.0 (v0.1 leaves it open)."""

    entity_id: str
    field: str
    reason: UnresolvedReason
    note: str = ""
    affects: list[str] = Field(default_factory=list)


class ImpactResult(BaseModel):
    schema_version: str = "1.0"
    disruption_id: str
    affected_entities: list[AffectedEntity] = Field(default_factory=list)
    checked_not_affected: list[CheckedNotAffected] = Field(default_factory=list)
    resource_shortfalls: list[ResourceShortfall] = Field(default_factory=list)
    unresolved_facts: list[UnresolvedFact] = Field(default_factory=list)
    # ---- extensions ----
    analysis_status: AnalysisStatus = AnalysisStatus.COMPLETE
    as_of: Optional[date] = None
    data_issues: list[DataIssue] = Field(default_factory=list)
    config: SeverityConfig = Field(default_factory=SeverityConfig)

    def to_contract(self) -> dict[str, Any]:
        """JSON-ready dict containing ONLY contract v0.1 fields."""
        return self.model_dump(
            mode="json",
            exclude={
                "analysis_status": True,
                "as_of": True,
                "data_issues": True,
                "config": True,
                "affected_entities": {
                    "__all__": {"priority", "severity_breakdown", "dependency_paths", "missing_information"}
                },
                "checked_not_affected": {"__all__": {"dependency_paths"}},
            },
        )
