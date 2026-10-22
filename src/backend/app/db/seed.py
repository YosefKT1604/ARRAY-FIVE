import json
from datetime import datetime, date, UTC
from pathlib import Path
from typing import Any

from sqlalchemy import select, func

from app.models.approval import Approval
from app.models.disruption import Disruption
from app.models.recovery_plan import RecoveryPlanRecord
from sqlalchemy.orm import Session

from app.db.database import engine, Base, SessionLocal
from app.models.delivery import Delivery
from app.models.dependency import Dependency
from app.models.job import Job
from app.models.resource import Resource
from app.models.supplier import Supplier, SupplierOffering

SEED_FILE = Path(__file__).resolve().parents[4] / "fixtures" / "demo" / "seed.json"

# Fixture key -> model, parents before children so foreign keys resolve.
TABLES = [
    ("resources", Resource),
    ("suppliers", Supplier),
    ("supplier_offerings", SupplierOffering),
    ("deliveries", Delivery),
    ("jobs", Job),
    ("dependencies", Dependency),
]
DATE_FIELDS = {"expected_date", "event_date", "deadline", "required_by"}
TIMESTAMP_FIELDS = {"verified_at", "confirmed_at"}

def parse_timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).astimezone(UTC) if value else None

def parse_row(row: dict[str, Any]) -> dict[str, Any]:
    parsed = dict(row)
    for field, value in row.items():
        if value is None:
            continue
        if field in DATE_FIELDS:
            parsed[field] = date.fromisoformat(value)
        elif field in TIMESTAMP_FIELDS:
            parsed[field] = parse_timestamp(value)
    return parsed

def load_fixture(session: Session) -> None:
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    for key, model in TABLES:
        session.add_all(model(**parse_row(row)) for row in data[key])
    session.commit()

def seed() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        load_fixture(session)

def seed_if_empty() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        if session.scalar(select(func.count()).select_from(Resource)) == 0:
            load_fixture(session)

if __name__ == "__main__":
    seed()
    print("Seeding complete")
