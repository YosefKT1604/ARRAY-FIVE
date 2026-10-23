"""Convert Person 2's shared contract objects (`contracts`) into the AI module's own shapes (`scdc.ai.schemas`).

Both sides copy the same CONTRACTS.md shapes, so the field names match and no field is mapped by hand.
Each object is written out as JSON-style data (what crosses the wire between modules) and read back with
our class. Our input classes ignore extra keys, so additions such as P3's `analysis_status` do no harm.

Only the inbound direction is needed: P2 has no extraction, explanation or draft types, so the AI
endpoints return our `ExtractionResult`, `Explanation` and `DraftMessage` as they are.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from scdc.ai.schemas import BusinessSnapshot, ImpactResult, NormalizedIncident, RecoveryPlan

AIModel = TypeVar("AIModel", bound=BaseModel)


def convert(value: BaseModel, target: type[AIModel]) -> AIModel:
    """Read any contract object as the given AI-module class, via its JSON form."""
    return target.model_validate(value.model_dump(mode="json"))


def ai_snapshot(snapshot: BaseModel) -> BusinessSnapshot:
    """P2's `contracts.BusinessSnapshot` as the AI module's BusinessSnapshot."""
    return convert(snapshot, BusinessSnapshot)


def ai_incident(incident: BaseModel) -> NormalizedIncident:
    """P2's `contracts.NormalizedIncident` as the AI module's NormalizedIncident."""
    return convert(incident, NormalizedIncident)


def ai_impact(impact: BaseModel) -> ImpactResult:
    """P2's (or P3's) `contracts.ImpactResult` as the AI module's ImpactResult."""
    return convert(impact, ImpactResult)


def ai_plans(plans: list[BaseModel]) -> list[RecoveryPlan]:
    """P2's `contracts.RecoveryPlan` list as the AI module's RecoveryPlan list, in the same order."""
    return [convert(plan, RecoveryPlan) for plan in plans]
