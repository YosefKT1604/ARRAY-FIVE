import json
from datetime import datetime, UTC
from pathlib import Path
from app.db.database import engine, Base, SessionLocal
from app.models.resource import Resource


SEED_FILE = Path(__file__).resolve().parents[4] / "fixtures" / "demo" / "seed.json"

def parse_timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).astimezone(UTC) if value else None

def seed() -> None:
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        session.add_all(
            Resource(**{**row, "verified_at": parse_timestamp(row["verified_at"])})
            for row in data["resources"]
        )
        session.commit()

if __name__ == "__main__":
    seed()
    print("Seeding complete")