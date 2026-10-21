from sqlalchemy.orm import Mapped, mapped_column
from datetime import date
from app.db.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    description: Mapped[str | None]
    customer_ref: Mapped[str | None]
    event_date: Mapped[date]
    deadline: Mapped[date]
    status: Mapped[str]
    priority: Mapped[str]