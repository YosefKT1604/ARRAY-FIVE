"""The safety guard around recovery plans: plans are only shown when they were made for THIS incident."""

import json
from pathlib import Path

import pytest

from app.models.disruption import Disruption
from app.services.recovery import placeholder_applies
from app.services.recovery_plan import no_plans_state
from contracts import ImpactResult, NormalizedIncident

DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "demo"
FORM = json.loads((DEMO / "incident.json").read_text(encoding="utf-8"))["form_input"]
API = "/api/v1"


@pytest.fixture(autouse=True)
def demo_day(monkeypatch):
    monkeypatch.setenv("SCDC_DEMO_NOW", "2026-10-20T08:00:00+08:00")


def report_and_analyze(client, **changes):
    client.post(f"{API}/disruptions", json={**FORM, **changes})
    return client.post(f"{API}/disruptions/D-001/analyze")


def skip_report_checks(monkeypatch):
    """Let an impossible report through creation, to reach an impact the engine cannot decide."""
    monkeypatch.setattr("app.routers.disruption.validate_report", lambda db, data: [])


def activity_types(client):
    return [entry["activity_type"] for entry in client.get(f"{API}/disruptions/D-001/activity-log").json()["items"]]


def test_demo_case_still_gets_the_three_plans(seeded_client):
    report_and_analyze(seeded_client)
    response = seeded_client.post(f"{API}/disruptions/D-001/recovery-plans")
    assert response.status_code == 201
    assert [p["id"] for p in response.json()["items"]] == ["RP-001", "RP-002", "RP-003"]
    assert response.json()["state"] is None
    assert seeded_client.get(f"{API}/disruptions/D-001").json()["plan_state"] is None


def test_a_smaller_delay_gets_no_plans_and_says_planning_is_not_available(seeded_client):
    """5 chairs late is a real shortfall, but the fixture plans were not made for it."""
    assert report_and_analyze(seeded_client, quantity_affected=5).status_code == 200
    response = seeded_client.post(f"{API}/disruptions/D-001/recovery-plans")
    assert response.status_code == 200
    assert response.json() == {"items": [], "state": "planning_not_available"}
    assert seeded_client.get(f"{API}/disruptions/D-001/recovery-plans").json() == response.json()
    disruption = seeded_client.get(f"{API}/disruptions/D-001").json()
    assert (disruption["status"], disruption["plan_state"]) == ("plans_ready", "planning_not_available")
    assert "plans_generated" in activity_types(seeded_client)


def test_nothing_affected_needs_no_recovery(seeded_client, session_factory):
    """A complete analysis that finds nothing affected says so, and logs it. (The demo data has no report that
    affects nothing, so the stored impact is replaced by a complete, empty one.)"""
    report_and_analyze(seeded_client)
    with session_factory() as db:
        disruption = db.get(Disruption, "D-001")
        disruption.impact = {**disruption.impact, "affected_entities": [], "resource_shortfalls": [], "analysis_status": "complete"}
        db.commit()
    response = seeded_client.post(f"{API}/disruptions/D-001/recovery-plans")
    assert response.status_code == 200
    assert response.json() == {"items": [], "state": "no_recovery_needed"}
    log = seeded_client.get(f"{API}/disruptions/D-001/activity-log").json()["items"]
    assert any(e["activity_type"] == "plans_generated" and e["details"]["state"] == "no_recovery_needed" for e in log)


def test_a_delay_of_zero_days_is_unclear_not_an_all_clear(seeded_client):
    """The impact engine marks a same-day arrival as partial (conflicting dates), so it is never called safe."""
    report_and_analyze(seeded_client, new_arrival_date=FORM["original_arrival_date"])
    assert seeded_client.get(f"{API}/disruptions/D-001/impact").json()["analysis_status"] == "partial"
    assert seeded_client.post(f"{API}/disruptions/D-001/recovery-plans").status_code == 409
    assert seeded_client.get(f"{API}/disruptions/D-001").json()["plan_state"] == "impact_unclear"


def test_an_undecided_impact_is_refused_and_remembered(seeded_client, monkeypatch):
    """More chairs than the delivery holds leaves the jobs unresolved: no plans, and the dashboard can say why."""
    skip_report_checks(monkeypatch)
    assert report_and_analyze(seeded_client, quantity_affected=50).status_code == 200
    response = seeded_client.post(f"{API}/disruptions/D-001/recovery-plans")
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE_TRANSITION"
    assert response.json()["detail"] == "The impact could not be decided; confirm the facts first."
    disruption = seeded_client.get(f"{API}/disruptions/D-001").json()
    assert (disruption["status"], disruption["plan_state"]) == ("analyzed", "impact_unclear")
    assert seeded_client.get(f"{API}/disruptions/D-001/recovery-plans").json() == {"items": [], "state": "impact_unclear"}


def test_analyzing_again_clears_the_state(seeded_client, monkeypatch):
    skip_report_checks(monkeypatch)
    report_and_analyze(seeded_client, quantity_affected=50)
    seeded_client.post(f"{API}/disruptions/D-001/recovery-plans")
    assert seeded_client.get(f"{API}/disruptions/D-001").json()["plan_state"] == "impact_unclear"
    seeded_client.post(f"{API}/disruptions/D-001/analyze")
    assert seeded_client.get(f"{API}/disruptions/D-001").json()["plan_state"] is None


def test_making_plans_clears_a_leftover_state(seeded_client, session_factory):
    report_and_analyze(seeded_client)
    with session_factory() as db:
        db.get(Disruption, "D-001").plan_state = "impact_unclear"
        db.commit()
    assert seeded_client.post(f"{API}/disruptions/D-001/recovery-plans").status_code == 201
    assert seeded_client.get(f"{API}/disruptions/D-001").json()["plan_state"] is None


# --- the pure decisions ------------------------------------------------------------


def demo_pair():
    incident = NormalizedIncident.model_validate(json.loads((DEMO / "incident.json").read_text(encoding="utf-8"))["expected_normalized_incident"])
    expected = json.loads((DEMO / "expected_impact.json").read_text(encoding="utf-8"))
    impact = ImpactResult.model_validate({k: v for k, v in expected.items() if k != "_note"})
    return incident, impact


def test_placeholder_applies_only_to_the_exact_demo_case():
    incident, impact = demo_pair()
    assert placeholder_applies(incident, impact)
    assert not placeholder_applies(incident.model_copy(update={"quantity_affected": 5}), impact)
    assert not placeholder_applies(incident.model_copy(update={"delivery_id": "DL-02"}), impact)
    changed = impact.model_copy(update={"resource_shortfalls": [impact.resource_shortfalls[0].model_copy(update={"shortfall": 5})]})
    assert not placeholder_applies(incident, changed)
    assert not placeholder_applies(incident, impact.model_copy(update={"resource_shortfalls": []}))


def test_a_potential_risk_alone_is_never_an_all_clear():
    incident, impact = demo_pair()
    risky = impact.affected_entities[0].model_copy(update={"impact_status": "potential_risk"})
    only_risk = impact.model_copy(update={"affected_entities": [risky], "resource_shortfalls": []})
    nothing = impact.model_copy(update={"affected_entities": [], "resource_shortfalls": []})
    assert no_plans_state(incident, only_risk) == "planning_not_available"
    assert no_plans_state(incident, nothing) == "no_recovery_needed"
    assert no_plans_state(incident, impact) is None
