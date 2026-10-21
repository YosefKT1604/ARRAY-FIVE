from fastapi import APIRouter

from app.schemas.item import ItemOut
from app.services.item import list_items
from app.dependencies import DbSession

router = APIRouter(prefix="/items", tags=["items"])

@router.get("/", response_model=list[ItemOut])
def get_items(db: DbSession):
    return list_items(db)