from pydantic import ConfigDict, BaseModel


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    total_quantity: int
    spare_quantity: int