import pytest


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
