import pytest
import json
from pathlib import Path

OWNER = {"X-User-Id": "U-01"}
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

# --- the connected planner (Person 4), on the demo day ---

@pytest.fixture
def demo_day(monkeypatch):
    # The planner takes the snapshot date as "today", so every recovery test pins the demo clock.
    monkeypatch.setenv("SCDC_DEMO_NOW", "2026-10-20T08:00:00+08:00")


def plans_for(client, **changes):
    client.post("/api/v1/disruptions", json={**FORM, **changes})
    client.post("/api/v1/disruptions/D-001/analyze")
    response = client.post("/api/v1/disruptions/D-001/recovery-plans")
    return response, {plan["id"]: plan for plan in response.json()["items"]}


def supplier_of(plan):
    return plan["actions"][0]["parameters"]["supplier_id"]


def check(plan, code):
    return next(c for c in plan["validation"]["checks"] if c["code"] == code)["result"]


def cahaya(plans):
    return next(p for p in plans.values() if supplier_of(p) == "S-02")


def test_demo_case_plans(seeded_client, demo_day):
    _, plans = plans_for(seeded_client)
    best = cahaya(plans)
    assert (best["validation"]["status"], best["rank"]) == ("feasible", 1)
    assert best["actions"][0]["parameters"]["quantity"] == 20
    assert best["estimated_cost"] == {"amount": "80.00", "currency": "MYR"}
    delima = next(p for p in plans.values() if supplier_of(p) == "S-03")
    assert delima["validation"]["status"] == "infeasible" and check(delima, "DEADLINE_MET") == "fail"
    maju = next(p for p in plans.values() if supplier_of(p) == "S-01")
    assert maju["validation"]["status"] == "needs_confirmation"
    for plan in plans.values():  # the IDs inside a plan agree with the plan
        assert plan["validation"]["plan_id"] == plan["id"]


def test_five_chairs_late(seeded_client, demo_day):
    _, plans = plans_for(seeded_client, quantity_affected=5)
    best = cahaya(plans)
    assert best["validation"]["status"] == "feasible" and best["actions"][0]["parameters"]["quantity"] == 5


def test_forty_chairs_late_has_no_feasible_plan(seeded_client, demo_day):
    _, plans = plans_for(seeded_client, quantity_affected=40)
    assert all(p["validation"]["status"] != "feasible" for p in plans.values())
    assert all(p["rank"] is None for p in plans.values())
    plan = cahaya(plans)
    assert plan["actions"][0]["parameters"]["quantity"] == 40
    assert check(plan, "SUPPLIER_AVAILABLE") == "fail"
    assert "25" in next(c for c in plan["validation"]["checks"] if c["code"] == "SUPPLIER_AVAILABLE")["detail"]


def test_edit_a_plan_makes_a_new_checked_version(seeded_client, demo_day):
    _, plans = plans_for(seeded_client)
    plan = cahaya(plans)
    action = {**plan["actions"][0], "parameters": {**plan["actions"][0]["parameters"], "quantity": 10}}
    url = f"/api/v1/recovery-plans/{plan['id']}"
    response = seeded_client.put(url, json={"base_version": 1, "actions": [action], "assumptions": plan["assumptions"]}, headers=OWNER)
    assert response.status_code == 200
    edited = response.json()
    assert edited["version"] == 2 and edited["validation"]["plan_version"] == 2
    assert edited["validation"]["status"] == "infeasible" and edited["rank"] is None
    assert check(edited, "QUANTITY_SUFFICIENT") == "fail"
    assert "short 10" in next(c for c in edited["validation"]["checks"] if c["code"] == "QUANTITY_SUFFICIENT")["detail"].lower()
    assert seeded_client.get(url).json()["version"] == 2

    stale = seeded_client.put(url, json={"base_version": 1, "actions": [action], "assumptions": []}, headers=OWNER)
    assert (stale.status_code, stale.json()["code"]) == (409, "STALE_PLAN_VERSION")
    log = [e["activity_type"] for e in seeded_client.get("/api/v1/disruptions/D-001/activity-log").json()["items"]]
    assert "plan_edited" in log


def test_old_version_is_kept_as_superseded_and_newest_can_be_approved(seeded_client, session_factory, demo_day):
    from app.models.recovery_plan import RecoveryPlanVersionRecord
    _, plans = plans_for(seeded_client)
    plan = cahaya(plans)
    url = f"/api/v1/recovery-plans/{plan['id']}"
    # Same quantity again: a new version that is still feasible.
    edited = seeded_client.put(url, json={"base_version": 1, "actions": plan["actions"], "assumptions": plan["assumptions"]}, headers=OWNER).json()
    assert edited["version"] == 2 and edited["validation"]["status"] == "feasible"
    with session_factory() as db:
        old = db.get(RecoveryPlanVersionRecord, (plan["id"], 1))
        assert old.plan["status"] == "superseded"
    wrong = seeded_client.post(f"{url}/approve", json={"plan_version": 1, "comments": ""}, headers=OWNER)
    assert wrong.status_code == 409 and wrong.json()["code"] == "STALE_PLAN_VERSION"
    approved = seeded_client.post(f"{url}/approve", json={"plan_version": 2, "comments": ""}, headers=OWNER)
    assert approved.status_code == 201
    again = seeded_client.put(url, json={"base_version": 2, "actions": plan["actions"], "assumptions": []}, headers=OWNER)
    assert again.status_code == 409


def test_revalidate_returns_the_same_plan_checked_again(seeded_client, demo_day):
    _, plans = plans_for(seeded_client)
    plan = cahaya(plans)
    response = seeded_client.post(f"/api/v1/recovery-plans/{plan['id']}/revalidate", headers=OWNER)
    assert response.status_code == 200
    assert response.json()["version"] == 1 and response.json()["validation"]["status"] == "feasible"
    log = [e["activity_type"] for e in seeded_client.get("/api/v1/disruptions/D-001/activity-log").json()["items"]]
    assert "plan_revalidated" in log
