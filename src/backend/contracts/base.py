from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class ContractModel(BaseModel):
    """Base for every shared shape: unknown fields are rejected, ORM rows are accepted."""
    model_config = ConfigDict(extra="forbid", from_attributes=True)

class Money(ContractModel):
    amount: Decimal
    currency: str