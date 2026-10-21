from pydantic import BaseModel
from contracts.entities import Job

class JobList(BaseModel):
    items: list[Job]