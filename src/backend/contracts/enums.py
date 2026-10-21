from enum import StrEnum

# Values from CONTRACTS.md §3 and §4. Only the enums the core path uses are defined so far.

class DisruptionType(StrEnum):
    SUPPLIER_DELAY = "supplier_delay"
    SUPPLIER_SHORTFALL = "supplier_shortfall"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    STAFF_ABSENCE = "staff_absence"

class InputSource(StrEnum):
    FORM = "form"
    MESSAGE = "message"

class EntityType(StrEnum):
    SUPPLIER = "supplier"
    DELIVERY = "delivery"
    RESOURCE = "resource"
    JOB = "job"
    COMMITMENT = "commitment"

class DependencyType(StrEnum):
    SHIPS = "ships"
    SUPPLIES = "supplies"
    REQUIRES = "requires"
    FULFILS = "fulfils"

class DeliveryStatus(StrEnum):
    SCHEDULED = "scheduled"
    DELAYED = "delayed"
    PARTIALLY_DELIVERED = "partially_delivered"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class UnresolvedReason(StrEnum):
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"
    CONFLICTING = "conflicting"
    UNVERIFIED = "unverified"

class ImpactStatus(StrEnum):
    CONFIRMED = "confirmed"
    POTENTIAL_RISK = "potential_risk"
    UNRESOLVED = "unresolved"

class ValidationStatus(StrEnum):
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    NEEDS_CONFIRMATION = "needs_confirmation"

class CheckResult(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNRESOLVED = "unresolved"

class CheckCode(StrEnum):
    RESOURCE_AVAILABLE = "RESOURCE_AVAILABLE"
    QUANTITY_SUFFICIENT = "QUANTITY_SUFFICIENT"
    SUPPLIER_AVAILABLE = "SUPPLIER_AVAILABLE"
    LEAD_TIME_OK = "LEAD_TIME_OK"
    DEADLINE_MET = "DEADLINE_MET"
    NO_DOUBLE_BOOKING = "NO_DOUBLE_BOOKING"
    DEPENDENCY_ORDER_OK = "DEPENDENCY_ORDER_OK"
    COMMITMENT_RESCHEDULABLE = "COMMITMENT_RESCHEDULABLE"
    FACTS_KNOWN = "FACTS_KNOWN"

class PlanStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    MORE_INFO_REQUESTED = "more_info_requested"
    SUPERSEDED = "superseded"

class PlanCreator(StrEnum):
    RULES = "rules"
    AI_SUGGESTION = "ai_suggestion"
    USER_EDIT = "user_edit"

class ActionType(StrEnum):
    USE_SPARE_INVENTORY = "use_spare_inventory"
    SOURCE_ALTERNATIVE_SUPPLIER = "source_alternative_supplier"
    REALLOCATE_RESOURCE = "reallocate_resource"
    RESCHEDULE_JOB = "reschedule_job"
    SPLIT_ALLOCATION = "split_allocation"
    CONTACT_SUPPLIER = "contact_supplier"

class ActionStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    COMPLETED = "completed"
    FAILED = "failed"