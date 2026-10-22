import json
from pathlib import Path

FORM = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "demo" / "incident.json").read_text(encoding="utf-8")
)["form_input"]
OWNER = {"X-User-Id": "U-01"}
STAFF = {"X-User-Id": "U-02"}
VERSION_1 = {"plan_version": 1}


def prepare_plans(client):
    client.post("/api/v1/disruptions", json=FORM)
    client.post("/api/v1/disruptions/D-001/analyze")
    client.post("/api/v1/disruptions/D-001/recovery-plans")

def test_owner_approves_feasible_plan(client):
    prepare_plans(client)

    response = client.post("/api/v1/recovery-plans/RP-001/approve", json=VERSION_1, headers=OWNER)
    assert response.status_code == 201

    approval = response.json()
    assert approval["decision"] == "approved"
    assert approval["reviewer_id"] == "U-01"

    plan = client.get("/api/v1/recovery-plans/RP-001").json()
    assert plan["status"] == "approved"

    disruption = client.get("/api/v1/disruptions/D-001").json()
    assert disruption["status"] == "decided"

def test_staff_cannot_approve(client):
    prepare_plans(client)

    response = client.post("/api/v1/recovery-plans/RP-001/approve", json=VERSION_1, headers=STAFF)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"

def test_approve_without_user_returns_401(client):
    prepare_plans(client)

    response = client.post("/api/v1/recovery-plans/RP-001/approve", json=VERSION_1)
    assert response.status_code == 401

def test_infeasible_plan_cannot_be_approved(client):
    prepare_plans(client)

    response = client.post("/api/v1/recovery-plans/RP-002/approve", json=VERSION_1, headers=OWNER)
    assert response.status_code == 409
    assert response.json()["code"] == "PLAN_INFEASIBLE"

def test_wrong_version_returns_409(client):
    prepare_plans(client)

    response = client.post("/api/v1/recovery-plans/RP-001/approve", json={"plan_version": 2}, headers=OWNER)
    assert response.status_code == 409
    assert response.json()["code"] == "STALE_PLAN_VERSION"

def test_owner_rejects_plan(client):
    prepare_plans(client)

    response = client.post("/api/v1/recovery-plans/RP-003/reject", json=VERSION_1, headers=OWNER)
    assert response.status_code == 201

    plan = client.get("/api/v1/recovery-plans/RP-003").json()
    assert plan["status"] == "rejected"

def test_plan_cannot_be_decided_twice(client):
    prepare_plans(client)
    client.post("/api/v1/recovery-plans/RP-001/approve", json=VERSION_1, headers=OWNER)

    response = client.post("/api/v1/recovery-plans/RP-001/approve", json=VERSION_1, headers=OWNER)
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE_TRANSITION"

def test_owner_requests_more_info(client):
    prepare_plans(client)

    response = client.post("/api/v1/recovery-plans/RP-001/request-info",
                           json={"plan_version": 1, "comments": "Is Cahaya's price confirmed?"}, headers=OWNER)
    assert response.status_code == 201
    assert response.json()["decision"] == "more_info_requested"
    assert client.get("/api/v1/recovery-plans/RP-001").json()["status"] == "more_info_requested"

def test_plan_can_be_approved_after_info_requested(client):
    prepare_plans(client)
    client.post("/api/v1/recovery-plans/RP-001/request-info", json={"plan_version": 1, "comments": "Is the price confirmed?"}, headers=OWNER)

    response = client.post("/api/v1/recovery-plans/RP-001/approve", json=VERSION_1, headers=OWNER)
    assert response.status_code == 201

def test_staff_cannot_request_info(client):
    prepare_plans(client)

    response = client.post("/api/v1/recovery-plans/RP-001/request-info", json={"plan_version": 1, "comments": "Is the price confirmed?"}, headers=STAFF)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"

def test_second_plan_cannot_be_approved(client):
    prepare_plans(client)
    client.post("/api/v1/recovery-plans/RP-001/approve", json=VERSION_1, headers=OWNER)

    response = client.post("/api/v1/recovery-plans/RP-003/approve", json=VERSION_1, headers=OWNER)
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE_TRANSITION"

def test_request_info_needs_a_comment(client):
    prepare_plans(client)

    response = client.post("/api/v1/recovery-plans/RP-001/request-info", json=VERSION_1, headers=OWNER)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"