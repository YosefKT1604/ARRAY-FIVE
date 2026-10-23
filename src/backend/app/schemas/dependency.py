from pydantic import BaseModel
from contracts.entities import Dependency

class DependencyList(BaseModel):
    items: list[Dependency]
