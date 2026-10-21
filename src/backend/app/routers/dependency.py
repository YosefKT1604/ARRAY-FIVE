from fastapi import APIRouter

from app.dependencies import DbSession
from app.schemas.dependency import DependencyList
from app.services.dependency import list_dependencies

router = APIRouter(prefix="/dependencies", tags=["dependencies"])

@router.get("", response_model=DependencyList)
def get_dependencies(db: DbSession) -> DependencyList:
    return DependencyList(items=list_dependencies(db))
