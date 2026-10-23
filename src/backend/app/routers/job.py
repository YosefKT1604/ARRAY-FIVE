from fastapi import APIRouter

from app.schemas.job import JobList
from app.dependencies import DbSession
from app.services.job import list_jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.get("", response_model=JobList)
def get_jobs(db: DbSession) -> JobList:
    return JobList(items=list_jobs(db))