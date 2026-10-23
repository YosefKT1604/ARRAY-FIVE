import pytest
import json
from pathlib import Path

FORM = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "demo" / "incident.json").read_text(encoding="utf-8")
)["form_input"]


def test_report_disruption_returns_201_with_incident(client):
    response = client.post("/api/v1/disruptions", json=FORM)
    assert response.status_code == 201
    body = response.json()
    assert body["disruption"]["id"] == "D-001"
    assert body["disruption"]["status"] == "received"
    assert body["incident"]["quantity_affected"] == 20

def test_list_and_get_disruption(client):
    client.post("/api/v1/disruptions", json=FORM)
    assert [d["id"] for d in client.get("/api/v1/disruptions").json()["items"]] == ["D-001"]
    assert client.get("/api/v1/disruptions/D-001").status_code == 200

def test_unknown_disruption_returns_404(client):
    assert client.get("/api/v1/disruptions/D-999").status_code == 404

@pytest.mark.usefixtures("seeded_client")  # the real impact engine needs the demo business data
def test_analyze_returns_impact_and_marks_disruption_analyzed(client):
    client.post("/api/v1/disruptions", json=FORM)
    response = client.post("/api/v1/disruptions/D-001/analyze")
    assert response.status_code == 200
    impact = response.json()
    assert impact["disruption_id"] == "D-001"
    assert impact["resource_shortfalls"][0]["shortfall"] == 20
    assert client.get("/api/v1/disruptions/D-001").json()["status"] == "analyzed"
    assert client.get("/api/v1/disruptions/D-001/impact").json() == impact

def test_impact_before_analysis_returns_404(client):
    client.post("/api/v1/disruptions", json=FORM)
    response = client.get("/api/v1/disruptions/D-001/impact")
    assert response.status_code == 404

def test_analyze_unknown_disruption_returns_404(client):
    response = client.post("/api/v1/disruptions/D-999/analyze")
    assert response.status_code == 404

@pytest.mark.usefixtures("seeded_client")  # the real impact engine needs the demo business data
def test_same_open_incident_returns_409(client):
    client.post("/api/v1/disruptions", json=FORM)
    # Still open after analysis, so a second identical report counts as a duplicate.
    response = client.post("/api/v1/disruptions/D-001/analyze")
    assert response.status_code == 200

    response = client.post("/api/v1/disruptions", json=FORM)
    assert response.status_code == 409
    assert response.json()["code"] == "DUPLICATE_DISRUPTION"
    assert "D-001" in response.json()["detail"]

def test_different_new_date_is_not_a_duplicate(client):
    client.post("/api/v1/disruptions", json=FORM)
    response = client.post("/api/v1/disruptions", json={**FORM, "new_arrival_date": "2026-10-24"})
    assert response.status_code == 201

@pytest.mark.usefixtures("seeded_client")  # the real impact engine needs the demo business data
def test_decided_disruption_can_be_reported_again(client):
    client.post("/api/v1/disruptions", json=FORM)
    client.post("/api/v1/disruptions/D-001/analyze")
    client.post("/api/v1/disruptions/D-001/recovery-plans")
    client.post("/api/v1/recovery-plans/RP-001/approve", json={"plan_version": 1}, headers={"X-User-Id": "U-01"})

    # Once a plan is approved the disruption is closed, so the same report is a new problem.
    response = client.post("/api/v1/disruptions", json=FORM)
    assert response.status_code == 201

def test_missing_material_field_needs_clarification(client):
    response = client.post("/api/v1/disruptions", json={**FORM, "quantity_affected": None})
    assert response.status_code == 201
    body = response.json()
    assert body["disruption"]["status"] == "needs_clarification"
    assert [f["field"] for f in body["incident"]["unresolved_fields"]] == ["quantity_affected"]

def test_needs_clarification_cannot_be_analyzed(client):
    client.post("/api/v1/disruptions", json={**FORM, "quantity_affected": None})

    response = client.post("/api/v1/disruptions/D-001/analyze")
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE_TRANSITION"

@pytest.mark.usefixtures("seeded_client")  # the real impact engine needs the demo business data
def test_decided_disruption_cannot_be_analyzed_again(client):
    client.post("/api/v1/disruptions", json=FORM)
    client.post("/api/v1/disruptions/D-001/analyze")
    client.post("/api/v1/disruptions/D-001/recovery-plans")
    client.post("/api/v1/recovery-plans/RP-001/approve", json={"plan_version": 1}, headers={"X-User-Id": "U-01"})

    response = client.post("/api/v1/disruptions/D-001/analyze")
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE_TRANSITION"

def test_zero_quantity_is_rejected(client):
    # Used to slip past the request schema and crash with a 500 when the incident was built.
    response = client.post("/api/v1/disruptions", json={**FORM, "quantity_affected": 0})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"

def test_unknown_method_has_error_code(client):
    response = client.delete("/api/v1/jobs")
    assert response.status_code == 405
    assert response.json()["code"] == "BAD_REQUEST"