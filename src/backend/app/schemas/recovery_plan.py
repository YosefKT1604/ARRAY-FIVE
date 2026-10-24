from enum import StrEnum

from typing import Any

from pydantic import BaseModel

from contracts import RecoveryPlan


# Why an analyzed disruption has no recovery plans. Backend-only (not in the shared contract): the list
# response carries it as an optional `state`, so clients that ignore it keep working.
class PlanState(StrEnum):
    NO_RECOVERY_NEEDED = "no_recovery_needed"
    PLANNING_NOT_AVAILABLE = "planning_not_available"
    IMPACT_UNCLEAR = "impact_unclear"


class RecoveryPlanList(BaseModel):
    items: list[RecoveryPlan]
    state: PlanState | None = None



# Body of PUT /recovery-plans/{id}. Actions stay plain dicts: the planner validates them and gives plain-word errors.
class PlanEdit(BaseModel):
    base_version: int
    actions: list[dict[str, Any]]
    assumptions: list[str] | None = None
