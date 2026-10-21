from datetime import date

from pydantic import ConfigDict, BaseModel


class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    supplier_id: str
    resource_id: str
    quantity: int
    expected_date: date
    status: str

class DeliveryList(BaseModel):
    items: list[DeliveryOut]
