import pytest
import json
from pathlib import Path

FORM = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "demo" / "incident.json").read_text(encoding="utf-8")
)["form_input"]


def report_and_analyze(client):
    client.post("/api/v1/disruptions", json=FORM)
    client.post("/api/v1/disruptions/D-001/analyze")

@pytest.mark.usefixtures("seeded_client")  # the real impact engine needs the demo business data
def test_generate_plans_returns_three_ranked_plans(client):
    report_and_analyze(client)

    response = client.post("/api/v1/disruptions/D-001/recovery-plans")
    assert response.status_code == 201

    plans = response.json()["items"]
    plan_ids = [plan["id"] for plan in plans]
    assert plan_ids == ["RP-001", "RP-002", "RP-003"]

    statuses = [plan["validation"]["status"] for plan in plans]
    assert statuses == ["feasible", "infeasible", "needs_confirmation"]

    disruption = client.get("/api/v1/disruptions/D-001").json()
    assert disruption["status"] == "plans_ready"

@pytest.mark.usefixtures("seeded_client")  # the real impact engine needs the demo business data
def test_list_plans_returns_saved_plans(client):
    report_and_analyze(client)
    created = client.post("/api/v1/disruptions/D-001/recovery-plans").json()

    listed = client.get("/api/v1/disruptions/D-001/recovery-plans").json()
    assert listed == created

@pytest.mark.usefixtures("seeded_client")  # reports are checked against the demo business data
def test_generate_plans_before_analysis_returns_409(client):
    client.post("/api/v1/disruptions", json=FORM)

    response = client.post("/api/v1/disruptions/D-001/recovery-plans")
    assert response.status_code == 409

@pytest.mark.usefixtures("seeded_client")  # reports are checked against the demo business data
def test_generate_plans_twice_returns_409(client):
    report_and_analyze(client)
    client.post("/api/v1/disruptions/D-001/recovery-plans")

    response = client.post("/api/v1/disruptions/D-001/recovery-plans")
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE_TRANSITION"

@pytest.mark.usefixtures("seeded_client")  # the real impact engine needs the demo business data
def test_get_one_plan(client):
    report_and_analyze(client)
    client.post("/api/v1/disruptions/D-001/recovery-plans")

    response = client.get("/api/v1/recovery-plans/RP-001")
    assert response.status_code == 200

    plan = response.json()
    assert plan["rank"] == 1
    assert plan["estimated_cost"] == {"amount": "80.00", "currency": "MYR"}

def test_get_unknown_plan_returns_404(client):
    response = client.get("/api/v1/recovery-plans/RP-999")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"