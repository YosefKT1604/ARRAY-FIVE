"""Reports that cannot be true are refused at creation, field by field, in plain words."""

import json
from pathlib import Path

import pytest

FORM = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "demo" / "incident.json").read_text(encoding="utf-8")
)["form_input"]
API = "/api/v1"


def refused(client, **changes):
    """Post a changed report that must be refused; return {field: message}."""
    response = client.post(f"{API}/disruptions", json={**FORM, **changes})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert client.get(f"{API}/disruptions").json()["items"] == []  # nothing was saved
    return {error["loc"][-1]: error["msg"] for error in body["errors"]}


def test_more_than_the_delivery_holds_is_refused(seeded_client):
    assert refused(seeded_client, quantity_affected=500) == {
        "quantity_affected": "500 chairs is more than the 40 on this delivery."}


def test_unknown_supplier_is_refused(seeded_client):
    # DL-01 belongs to S-01, but an unknown supplier is reported on its own field only.
    assert refused(seeded_client, supplier_id="S-99") == {"supplier_id": "We don't know that supplier."}


def test_an_item_the_delivery_does_not_carry_is_refused(seeded_client):
    """R-02 (tables) exists, but DL-01 carries chairs."""
    assert refused(seeded_client, resource_id="R-02") == {"delivery_id": "This order does not include the item you chose."}


def test_unknown_resource_and_delivery_are_refused(seeded_client):
    assert refused(seeded_client, resource_id="R-99") == {"resource_id": "We don't know that item."}
    assert refused(seeded_client, delivery_id="DL-99") == {"delivery_id": "We don't know that order."}


def test_a_delivery_from_another_supplier_is_refused(seeded_client):
    assert refused(seeded_client, supplier_id="S-02") == {"delivery_id": "This order is not from the supplier you chose."}


def test_a_new_date_before_the_due_date_is_refused(seeded_client):
    assert refused(seeded_client, new_arrival_date="2026-10-20") == {
        "new_arrival_date": "The new date cannot be earlier than the date it was due."}


def test_every_wrong_field_is_reported_at_once(seeded_client):
    errors = refused(seeded_client, supplier_id="S-99", resource_id="R-99", quantity_affected=500, new_arrival_date="2026-10-01")
    assert set(errors) == {"supplier_id", "resource_id", "quantity_affected", "new_arrival_date"}


def test_missing_fields_still_need_clarification_not_a_refusal(seeded_client):
    response = seeded_client.post(f"{API}/disruptions", json={**FORM, "quantity_affected": None, "supplier_id": None})
    assert response.status_code == 201
    assert response.json()["disruption"]["status"] == "needs_clarification"


@pytest.mark.parametrize("changes", [{}, {"delivery_id": None, "original_arrival_date": None}])
def test_a_valid_report_is_accepted(seeded_client, changes):
    assert seeded_client.post(f"{API}/disruptions", json={**FORM, **changes}).status_code == 201
