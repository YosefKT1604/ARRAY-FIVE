import json
from pathlib import Path

FORM = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "demo" / "incident.json").read_text(encoding="utf-8")
)["form_input"]
OWNER = {"X-User-Id": "U-01"}
STAFF = {"X-User-Id": "U-02"}
VERSION_1 = {"plan_version": 1}


def run_demo_flow(client):
    client.post("/api/v1/disruptions", json=FORM)
    client.post("/api/v1/disruptions/D-001/analyze")
    client.post("/api/v1/disruptions/D-001/recovery-plans")
    client.post("/api/v1/recovery-plans/RP-001/approve", json=VERSION_1, headers=STAFF)
    client.post("/api/v1/recovery-plans/RP-001/approve", json=VERSION_1, headers=OWNER)

def test_activity_log_records_demo_flow_oldest_first(seeded_client):
    run_demo_flow(seeded_client)

    response = seeded_client.get("/api/v1/disruptions/D-001/activity-log")
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["activity_type"] for item in items] == [
        "disruption_reported", "analysis_completed", "plans_generated", "approval_denied", "plan_approved",
    ]

def test_denied_approval_is_logged_with_actor_and_plan(seeded_client):
    run_demo_flow(seeded_client)

    items = seeded_client.get("/api/v1/disruptions/D-001/activity-log").json()["items"]
    denied = items[3]
    assert denied["actor_id"] == "U-02"
    assert denied["plan_id"] == "RP-001"

def test_rejection_is_logged(seeded_client):
    run_demo_flow(seeded_client)
    seeded_client.post("/api/v1/recovery-plans/RP-003/reject", json=VERSION_1, headers=OWNER)

    items = seeded_client.get("/api/v1/disruptions/D-001/activity-log").json()["items"]
    assert items[-1]["activity_type"] == "plan_rejected"
    assert items[-1]["plan_id"] == "RP-003"

def test_activity_log_for_unknown_disruption_returns_404(client):
    response = client.get("/api/v1/disruptions/D-999/activity-log")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"

def test_activity_log_ids_and_timestamps_follow_contract(seeded_client):
    run_demo_flow(seeded_client)

    first = seeded_client.get("/api/v1/disruptions/D-001/activity-log").json()["items"][0]
    assert first["id"] == "LOG-0001"
    assert first["created_at"].endswith("Z")
