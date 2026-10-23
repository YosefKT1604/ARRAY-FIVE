from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dependency import Dependency


def list_dependencies(db: Session) -> list[Dependency]:
    return list(db.scalars(select(Dependency).order_by(Dependency.id)))