from datetime import date

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[str] = mapped_column(primary_key=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"))
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"))
    quantity: Mapped[int]
    expected_date: Mapped[date]
    status: Mapped[str]
