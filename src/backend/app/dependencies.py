from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import SessionLocal


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session

DbSession = Annotated[Session, Depends(get_db)]