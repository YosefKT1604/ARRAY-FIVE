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
    # None when impact_status is "unresolved": the engine cannot score what it cannot confirm.
    severity: int | None = Field(ge=0, le=10)
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
    # Extensions proposed by P3 (impact_engine INTEGRATION.md §7). "partial" means some data was missing or
    # rejected, so an entity missing from affected_entities is not proof it is safe; data_issues says why.
    analysis_status: Literal["complete", "partial", "failed"] | None = None
    data_issues: list[dict[str, Any]] = []