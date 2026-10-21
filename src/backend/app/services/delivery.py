from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.delivery import Delivery


def list_deliveries(db: Session) -> list[Delivery]:
    return list(db.scalars(select(Delivery).order_by(Delivery.id)))
