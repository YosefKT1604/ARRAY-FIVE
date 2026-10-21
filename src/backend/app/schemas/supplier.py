from pydantic import BaseModel
from contracts.entities import Supplier, SupplierOffering


class SupplierWithOfferings(Supplier):
    offerings: list[SupplierOffering]

class SupplierList(BaseModel):
    items: list[SupplierWithOfferings]
