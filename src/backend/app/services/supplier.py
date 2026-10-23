from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.supplier import Supplier


def list_suppliers(db: Session) -> list[Supplier]:
    query = select(Supplier).options(selectinload(Supplier.offerings)).order_by(Supplier.id)
    return list(db.scalars(query))
