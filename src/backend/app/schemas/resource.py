from datetime import datetime

from pydantic import ConfigDict, BaseModel


class ResourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    aliases: list[str]
    unit: str
    owned_quantity: int
    on_hand_quantity: int
    on_hand_verified: bool
    verified_at: datetime | None
    reusable: bool

class ResourceList(BaseModel):
    items: list[ResourceOut]