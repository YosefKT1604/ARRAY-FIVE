from datetime import date

from pydantic import ConfigDict, BaseModel


class DependencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    dependency_type: str
    required_quantity: int | None
    required_by: date | None

class DependencyList(BaseModel):
    items: list[DependencyOut]
