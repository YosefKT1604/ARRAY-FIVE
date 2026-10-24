"""Tests for the AI endpoints in P2's backend (app/routers/ai.py), using P2's seeded test client.

No test reaches a real model: the adapter dependency is replaced by NoModelAdapter (or a MockAdapter).
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from app.main import app
from app.services import ai as ai_service
from scdc.ai.adapter import MockAdapter, NoModelAdapter

from .conftest import DEMO_FIXTURES, DEMO_MESSAGE

FORM = json.loads((DEMO_FIXTURES / "incident.json").read_text(encoding="utf-8"))["form_input"]
OWNER = {"X-User-Id": "U-01"}
STAFF = {"X-User-Id": "U-02"}
MAJU = "whatsapp:maju-rental (synthetic)"
API = "/api/v1"


@pytest.fixture(autouse=True)
def no_model():
    """Every request uses NoModelAdapter unless a test sets its own adapter."""
    app.dependency_overrides[ai_service.get_ai_adapter] = NoModelAdapter
    yield
    app.dependency_overrides.pop(ai_service.get_ai_adapter, None)


@pytest.fixture
def demo_clock(monkeypatch):
    """Freeze the report time at the demo's: Tuesday 20 Oct 2026, 10:15 Malaysia time."""
    monkeypatch.setattr(ai_service, "report_time", lambda: datetime(2026, 10, 20, 10, 15, tzinfo=ai_service.MALAYSIA))


def analyzed(client) -> None:
    """Report the demo incident and analyze it (no plans yet)."""
    client.post(f"{API}/disruptions", json=FORM)
    client.post(f"{API}/disruptions/D-001/analyze")


def approved_rp001(client) -> None:
    """Report, analyze, generate plans and approve RP-001 (the feasible plan)."""
    analyzed(client)
    client.post(f"{API}/disruptions/D-001/recovery-plans")
    client.post(f"{API}/recovery-plans/RP-001/approve", json={"plan_version": 1}, headers=OWNER)


# --- POST /disruptions/extract ------------------------------------------------------


def test_extract_demo_message_from_maju(seeded_client, demo_clock):
    """The demo WhatsApp message from Maju's contact prefills every field of the demo incident."""
    response = seeded_client.post(f"{API}/disruptions/extract", json={"message": DEMO_MESSAGE, "from_contact": MAJU})
    assert response.status_code == 200
    body = response.json()
    draft = body["draft_incident"]
    assert (draft["supplier_id"], draft["resource_id"], draft["delivery_id"]) == ("S-01", "R-01", "DL-01")
    assert (draft["quantity_affected"], draft["new_arrival_date"]) == (20, "2026-10-23")
    assert body["needs_clarification"] is False
    assert body["generated_by"] == "template"


def test_demo_clock_setting_is_used_for_extraction(seeded_client, monkeypatch):
    """With SCDC_DEMO_NOW on the demo day, "Friday" in the demo message is 23 Oct, whatever today is."""
    monkeypatch.setenv("SCDC_DEMO_NOW", "2026-10-20T10:15:00+08:00")
    body = seeded_client.post(f"{API}/disruptions/extract", json={"message": DEMO_MESSAGE, "from_contact": MAJU}).json()
    assert body["draft_incident"]["new_arrival_date"] == "2026-10-23"
    assert body["draft_incident"]["reported_at"] == "2026-10-20T10:15:00+08:00"


def test_extract_stores_nothing(seeded_client, demo_clock):
    """Extraction only prefills the form: no disruption is created."""
    seeded_client.post(f"{API}/disruptions/extract", json={"message": DEMO_MESSAGE, "from_contact": MAJU})
    assert seeded_client.get(f"{API}/disruptions").json()["items"] == []


def test_extract_without_sender_leaves_supplier_for_the_owner(seeded_client, demo_clock):
    """Without `from_contact` the message names no supplier, so the field is left blank and flagged."""
    body = seeded_client.post(f"{API}/disruptions/extract", json={"message": DEMO_MESSAGE}).json()
    assert body["draft_incident"]["supplier_id"] is None
    assert body["needs_clarification"] is True


def test_extract_with_sender_does_not_ask_for_the_supplier(seeded_client, demo_clock):
    """A known sender fills the supplier, so the "does not name any known suppliers" question is not asked."""
    body = seeded_client.post(f"{API}/disruptions/extract", json={"message": DEMO_MESSAGE, "from_contact": MAJU}).json()
    assert body["draft_incident"]["supplier_id"] == "S-01"
    assert "supplier_id" not in [u["field"] for u in body["unresolved_fields"]]
    assert not any("known suppliers" in q for q in body["clarification_questions"])


def test_extract_falls_back_when_the_model_reply_is_broken(seeded_client, demo_clock):
    """A broken model reply never fails the request: the rule-based reading is returned with a warning."""
    adapter = MockAdapter({"*": "this is not JSON"})
    app.dependency_overrides[ai_service.get_ai_adapter] = lambda: adapter
    body = seeded_client.post(f"{API}/disruptions/extract", json={"message": DEMO_MESSAGE, "from_contact": MAJU}).json()
    assert len(adapter.calls) == 1
    assert body["fallback_used"] is True and body["warnings"]
    assert body["draft_incident"]["supplier_id"] == "S-01"


# --- GET /disruptions/{id}/explanation -------------------------------------------------


def test_explanation_compares_every_plan_with_copied_status(seeded_client):
    """The explanation covers all three plans; each validation status is copied from the plan."""
    analyzed(seeded_client)
    plans = seeded_client.post(f"{API}/disruptions/D-001/recovery-plans").json()["items"]
    response = seeded_client.get(f"{API}/disruptions/D-001/explanation")
    assert response.status_code == 200
    body = response.json()
    statuses = {c["plan_id"]: c["validation_status"] for c in body["plan_comparisons"]}
    assert statuses == {p["id"]: p["validation"]["status"] for p in plans}
    assert (body["disruption_id"], body["generated_by"]) == ("D-001", "template")


def test_explanation_before_plans_explains_the_impact(seeded_client):
    """Analyzed but no plans yet: still 200, with no plan comparisons."""
    analyzed(seeded_client)
    body = seeded_client.get(f"{API}/disruptions/D-001/explanation").json()
    assert body["plan_comparisons"] == []
    assert body["summary"]


def test_explanation_needs_an_analyzed_disruption(seeded_client):
    """Before analysis there is nothing to explain: 409; an unknown disruption is 404."""
    seeded_client.post(f"{API}/disruptions", json=FORM)
    response = seeded_client.get(f"{API}/disruptions/D-001/explanation")
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE_TRANSITION"
    assert seeded_client.get(f"{API}/disruptions/D-404/explanation").status_code == 404


# --- POST /recovery-plans/{id}/drafts, POST /drafts/{id}/approve -------------------------


def test_drafts_for_approved_plan(seeded_client):
    """RP-001 (rent from Cahaya) gets one supplier draft, numbered DM-001, with placeholders to fill in."""
    approved_rp001(seeded_client)
    response = seeded_client.post(f"{API}/recovery-plans/RP-001/drafts", headers=OWNER)
    assert response.status_code == 201
    drafts = response.json()["items"]
    assert [(d["id"], d["recipient_type"], d["recipient_id"], d["status"]) for d in drafts] == [
        ("DM-001", "supplier", "S-02", "draft")]
    assert "YOUR_NAME" in drafts[0]["placeholders"]


def test_asking_for_drafts_twice_returns_the_same_drafts(seeded_client):
    """A second request returns the stored drafts instead of new ones."""
    approved_rp001(seeded_client)
    first = seeded_client.post(f"{API}/recovery-plans/RP-001/drafts").json()["items"]
    second = seeded_client.post(f"{API}/recovery-plans/RP-001/drafts").json()["items"]
    assert first == second


def test_no_drafts_for_a_plan_that_is_not_approved(seeded_client):
    """A proposed plan gets 409; an unknown plan gets 404."""
    analyzed(seeded_client)
    seeded_client.post(f"{API}/disruptions/D-001/recovery-plans")
    response = seeded_client.post(f"{API}/recovery-plans/RP-001/drafts")
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE_TRANSITION"
    assert seeded_client.post(f"{API}/recovery-plans/RP-404/drafts").status_code == 404


def test_owner_approves_draft_and_it_is_logged(seeded_client):
    """Approving marks the draft approved (twice is fine) and both steps appear in the activity log."""
    approved_rp001(seeded_client)
    seeded_client.post(f"{API}/recovery-plans/RP-001/drafts", headers=OWNER)
    response = seeded_client.post(f"{API}/drafts/DM-001/approve", headers=OWNER)
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert seeded_client.post(f"{API}/drafts/DM-001/approve", headers=OWNER).json()["status"] == "approved"

    log = seeded_client.get(f"{API}/disruptions/D-001/activity-log").json()["items"]
    entries = [(e["activity_type"], e["actor_id"], e["details"]) for e in log if e["activity_type"].startswith("draft")]
    assert entries == [("draft_created", "U-01", {"draft_ids": ["DM-001"]}),
                       ("draft_approved", "U-01", {"draft_id": "DM-001"})]


def test_only_the_owner_approves_drafts(seeded_client):
    """Staff get 403, no user 401, an unknown draft 404; the draft stays a draft."""
    approved_rp001(seeded_client)
    seeded_client.post(f"{API}/recovery-plans/RP-001/drafts")
    assert seeded_client.post(f"{API}/drafts/DM-001/approve", headers=STAFF).status_code == 403
    assert seeded_client.post(f"{API}/drafts/DM-001/approve").status_code == 401
    assert seeded_client.post(f"{API}/drafts/DM-404/approve", headers=OWNER).status_code == 404
    drafts = seeded_client.post(f"{API}/recovery-plans/RP-001/drafts").json()["items"]
    assert drafts[0]["status"] == "draft"
