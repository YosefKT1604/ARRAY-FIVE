import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.db.database import Base
from app.db.seed import load_fixture
from app.dependencies import get_db
from app.main import app

@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)

@pytest.fixture
def client(session_factory):
    def override_get_db():
        with session_factory() as session:
         yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
      yield c
    app.dependency_overrides.clear()

@pytest.fixture
def seeded_client(client, session_factory):
    with session_factory() as session:
        load_fixture(session)
    return client