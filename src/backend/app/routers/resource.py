from fastapi import APIRouter

from app.dependencies import DbSession
from app.schemas.resource import ResourceList
from app.services.resource import list_resources

router = APIRouter(prefix="/resources", tags=["resources"])

@router.get("", response_model=ResourceList)
def get_resources(db: DbSession) -> ResourceList:
    return ResourceList(items=list_resources(db))