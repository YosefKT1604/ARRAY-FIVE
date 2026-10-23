from fastapi import APIRouter

from app.dependencies import DbSession
from app.schemas.supplier import SupplierList
from app.services.supplier import list_suppliers

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

@router.get("", response_model=SupplierList)
def get_suppliers(db: DbSession) -> SupplierList:
    return SupplierList(items=list_suppliers(db))
