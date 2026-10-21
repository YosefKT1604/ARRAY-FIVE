from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.resource import Resource


def list_resources(db: Session) -> list[Resource]:
    return list(db.scalars(select(Resource).order_by(Resource.id)))
