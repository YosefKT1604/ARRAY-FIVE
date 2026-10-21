from pydantic import BaseModel
from contracts.entities import Resource

class ResourceList(BaseModel):
    items: list[Resource]