"""P3's impact engine running inside P2's backend: the analyze endpoint, failures, unknowns and the demo clock."""

import json
from pathlib import Path

import pytest

from app.main import app
from app.services import ai as ai_service
from scdc.ai.adapter import NoModelAdapter

FORM = json.loads(
    (Path(__file__).resolve().parents[2] / "fixtures" / "demo" / "incident.json").read_text(encoding="utf-8")
)["form_input"]
API = "/api/v1"


@pytest.fixture(autouse=True)
def demo_day(monkeypatch):
    """Run every test on the demo day, and with no AI model, whatever the real date and .env say."""
    monkeypatch.setenv("SCDC_DEMO_NOW", "2026-10-20T08:00:00+08:00")
    app.dependency_overrides[ai_service.get_ai_adapter] = NoModelAdapter
    yield
    app.dependency_overrides.pop(ai_service.get_ai_adapter, None)


def report_and_analyze(client, **changes):
    """Report the demo incident (optionally changed) and analyze it; return the analyze response."""
    client.post(f"{API}/disruptions", json={**FORM, **changes})
    return client.post(f"{API}/disruptions/D-001/analyze")


def test_demo_impact_comes_from_the_real_engine(seeded_client):
    """The engine finds the demo's affected records and the 20-chair shortfall, and reports a complete run."""
    response = report_and_analyze(seeded_client)
    assert response.status_code == 200
    impact = response.json()
    statuses = {e["entity_id"]: e["impact_status"] for e in impact["affected_entities"]}
    assert statuses == {"R-01": "confirmed", "J-01": "confirmed", "J-02": "confirmed",
                        "CM-01": "confirmed", "CM-02": "confirmed"}
    assert {c["entity_id"] for c in impact["checked_not_affected"]} == {"J-03", "CM-03"}
    assert impact["resource_shortfalls"] == [
        {"resource_id": "R-01", "date": "2026-10-22", "required": 70, "available": 50, "shortfall": 20}]
    assert (impact["analysis_status"], impact["data_issues"]) == ("complete", [])


def test_demo_clock_sets_report_time_and_scores(seeded_client):
    """With SCDC_DEMO_NOW the report is dated on the demo day, and the scores are measured from it."""
    created = seeded_client.post(f"{API}/disruptions", json=FORM).json()
    assert created["incident"]["reported_at"] == "2026-10-20T00:00:00Z"
    impact = seeded_client.post(f"{API}/disruptions/D-001/analyze").json()
    assert {e["entity_id"]: e["severity"] for e in impact["affected_entities"] if e["entity_type"] == "job"} == {
        "J-01": 6, "J-02": 6}


def test_failed_analysis_is_an_error_and_changes_nothing(seeded_client):
    """An incident about a delivery that doesn't exist cannot be analyzed: 422, still `received`, no impact."""
    response = report_and_analyze(seeded_client, delivery_id="DL-99")
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert "DL-99" in response.json()["detail"]
    assert seeded_client.get(f"{API}/disruptions/D-001").json()["status"] == "received"
    assert seeded_client.get(f"{API}/disruptions/D-001/impact").status_code == 404


def test_unknown_severity_is_stored_as_null(seeded_client):
    """A delay larger than the delivery leaves the jobs unresolved: no severity, run marked partial."""
    response = report_and_analyze(seeded_client, quantity_affected=50)
    assert response.status_code == 200
    impact = response.json()
    unresolved = [e for e in impact["affected_entities"] if e["impact_status"] == "unresolved"]
    assert unresolved and all(e["severity"] is None for e in unresolved)
    assert impact["analysis_status"] == "partial" and impact["data_issues"]
    assert seeded_client.get(f"{API}/disruptions/D-001/impact").json() == impact


def test_explanation_works_on_the_real_impact(seeded_client):
    """Module B explains the engine's output: one text per affected record."""
    report_and_analyze(seeded_client)
    seeded_client.post(f"{API}/disruptions/D-001/recovery-plans")
    body = seeded_client.get(f"{API}/disruptions/D-001/explanation").json()
    assert {i["entity_id"] for i in body["impact_explanations"]} == {"R-01", "J-01", "J-02", "CM-01", "CM-02"}
