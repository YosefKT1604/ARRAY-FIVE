from app.db.database import engine, Base, SessionLocal
from app.models.item import Item


def seed() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        session.add_all([
            Item(id="I-001",  name="Folding chair", total_quantity=200, spare_quantity=20),
            # insert this once mock data is ready
        ])
        session.commit()

if __name__ == "__main__":
    seed()
    print("Seeding complete")