import pytest
from sqlalchemy import select
from app.db.seed import load_fixture
from app.models.commitment import Commitment


@pytest.mark.parametrize(("path", "count"), [
    ("/resources", 2),
    ("/suppliers", 3),
    ("/deliveries", 1),
    ("/jobs", 3),
    ("/dependencies", 9),
])
def test_list_endpoints_return_seeded_items(seeded_client, path, count):
    response = seeded_client.get(f"/api/v1{path}")
    assert response.status_code == 200
    assert len(response.json()["items"]) == count

def test_suppliers_embed_offerings_with_money_as_string(seeded_client):
    supplier = seeded_client.get("/api/v1/suppliers").json()["items"][0]
    assert supplier["id"] == "S-01"
    assert supplier["offerings"][0]["unit_cost"] == {"amount": "3.50", "currency": "MYR"}

def test_dates_are_returned_as_iso_strings(seeded_client):
    delivery = seeded_client.get("/api/v1/deliveries").json()["items"][0]
    assert delivery["expected_date"] == "2026-10-21"

def test_seed_loads_commitments(session_factory):
    with session_factory() as session:
        load_fixture(session)
        commitments = session.scalars(select(Commitment).order_by(Commitment.id)).all()

    assert [c.id for c in commitments] == ["CM-01", "CM-02", "CM-03"]
    assert commitments[0].reschedulable is False
