from pydantic import BaseModel
from contracts.entities import Delivery

class DeliveryList(BaseModel):
    items: list[Delivery]
