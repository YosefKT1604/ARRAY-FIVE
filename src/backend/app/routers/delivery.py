from fastapi import APIRouter

from app.dependencies import DbSession
from app.schemas.delivery import DeliveryList
from app.services.delivery import list_deliveries

router = APIRouter(prefix="/deliveries", tags=["deliveries"])

@router.get("", response_model=DeliveryList)
def get_deliveries(db: DbSession) -> DeliveryList:
    return DeliveryList(items=list_deliveries(db))
