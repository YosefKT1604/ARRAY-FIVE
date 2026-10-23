from enum import StrEnum

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
