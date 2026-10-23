from datetime import date

from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base

class Dependency(Base):
    __tablename__ = "dependencies"

    id: Mapped[str] = mapped_column(primary_key=True)
    source_type: Mapped[str]
    source_id: Mapped[str]
    target_type: Mapped[str]
    target_id: Mapped[str]
    dependency_type: Mapped[str]
    required_quantity: Mapped[int | None]
    required_by: Mapped[date| None]