from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from contracts.enums import ActivityType


class ActivityLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    disruption_id: str
    plan_id: str | None
    actor_id: str
    activity_type: ActivityType
    details: dict[str, Any]
    created_at: datetime

class ActivityLogList(BaseModel):
    items: list[ActivityLogOut]
