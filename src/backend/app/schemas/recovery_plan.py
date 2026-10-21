from pydantic import BaseModel

from contracts import RecoveryPlan


class RecoveryPlanList(BaseModel):
    items: list[RecoveryPlan]