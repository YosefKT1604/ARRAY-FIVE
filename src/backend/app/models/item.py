from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

class Item(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    total_quantity: Mapped[int]
    spare_quantity: Mapped[int]

    