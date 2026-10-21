from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from contracts.base import ContractModel, Money
from contracts.enums import (
    ActionStatus, ActionType, CheckCode, CheckResult, EntityType, PlanCreator, PlanStatus, ValidationStatus,
)


class EntityRef(ContractModel):
    entity_type: EntityType
    entity_id: str

class RecoveryAction(ContractModel):
    id: str
    action_type: ActionType
    target_entity: EntityRef
    parameters: dict[str, Any]
    status: ActionStatus

class Check(ContractModel):
    code: CheckCode
    result: CheckResult
    detail: str
    evidence_ids: list[str] = []

class ValidationResult(ContractModel):
    plan_id: str
    plan_version: int
    status: ValidationStatus
    checks: list[Check]
    unresolved_assumptions: list[str] = []
    validated_at: datetime | None = None

class RecoveryPlan(ContractModel):
    # tailor for debugging
    schema_version: Literal["1.0"] = "1.0"
    id: str
    disruption_id: str
    version: int = Field(ge=1)
    summary: str
    actions: list[RecoveryAction]
    assumptions: list[str] = []
    estimated_cost: Money | None = None
    validation: ValidationResult | None = None
    rank: int | None = None
    status: PlanStatus
    created_by: PlanCreator