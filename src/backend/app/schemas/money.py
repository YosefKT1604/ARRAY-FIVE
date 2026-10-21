from decimal import Decimal

from pydantic import BaseModel


class Money(BaseModel):
    amount: Decimal
    currency: str
