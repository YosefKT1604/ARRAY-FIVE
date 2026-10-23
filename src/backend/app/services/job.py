from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job

def list_jobs(db: Session) -> list[Job]:
    return list(db.scalars(select(Job).order_by(Job.id)))
