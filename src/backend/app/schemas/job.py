from datetime import date

from pydantic import ConfigDict, BaseModel


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    customer_ref: str | None
    event_date: date
    deadline: date
    status: str
    priority: str

class JobList(BaseModel):
    items: list[JobOut]