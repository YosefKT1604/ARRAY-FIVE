import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.db.database import Base
from app.dependencies import get_db
from app.main import app

@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    def override_get_db():
        with TestingSession() as session:
         yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
      yield c
    app.dependency_overrides.clear()