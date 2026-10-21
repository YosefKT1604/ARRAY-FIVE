from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.item import Item


def list_items(db: Session) -> list[Item]:
    return list(db.scalars(select(Item).order_by(Item.id)))
