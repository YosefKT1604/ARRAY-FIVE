from datetime import date
from typing import Any, Literal

from pydantic import Field

from contracts.base import ContractModel, Quantity
from contracts.enums import EntityType, ImpactStatus


class Evidence(ContractModel):
    entity_id: str
    fact: str

class AffectedEntity(ContractModel):
    entity_type: EntityType
    entity_id: str
    impact_status: ImpactStatus
    severity: int = Field(ge=0, le=10)
    reason: str
    dependency_path: list[str]
    evidence: list[Evidence] = []

class CheckedNotAffected(ContractModel):
    entity_type: EntityType
    entity_id: str
    reason: str

class ResourceShortfall(ContractModel):
    resource_id: str
    date: date
    required: Quantity
    available: Quantity
    shortfall: Quantity

class ImpactResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    disruption_id: str
    affected_entities: list[AffectedEntity]
    checked_not_affected: list[CheckedNotAffected] = []
    resource_shortfalls: list[ResourceShortfall] = []
    unresolved_facts: list[dict[str, Any]] = []