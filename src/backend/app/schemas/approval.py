from pydantic import BaseModel, ConfigDict
from contracts import Decision
from datetime import datetime


class DecisionRequest(BaseModel):
    plan_version: int
    comments: str = ""

class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    plan_id: str
    plan_version: int
    reviewer_id: str
    decision: Decision
    comments: str
    decided_at: datetime