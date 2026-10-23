from datetime import date

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

class Commitment(Base):
    __tablename__ = "commitments"

    id: Mapped[str] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    commitment_type: Mapped[str]
    required_date: Mapped[date]
    reschedulable: Mapped[bool]
    status: Mapped[str]