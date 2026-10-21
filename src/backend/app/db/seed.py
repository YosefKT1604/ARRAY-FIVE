from app.db.database import engine, Base, SessionLocal
from app.models.resource import Resource


def seed() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        session.add_all([
            # insert this once mock data is ready
        ])
        session.commit()

if __name__ == "__main__":
    seed()
    print("Seeding complete")