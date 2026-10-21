from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Quantity = Annotated[int, Field(ge=0)]

class ContractModel(BaseModel):
    """Base for every shared shape: unknown fields are rejected, ORM rows are accepted."""
    model_config = ConfigDict(extra="forbid", from_attributes=True)

class Money(ContractModel):
    amount: Decimal
    currency: str
