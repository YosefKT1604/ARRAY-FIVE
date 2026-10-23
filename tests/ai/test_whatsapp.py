"""Tests for the WhatsApp inbox endpoints (app/routers/whatsapp.py), fed by the in-app simulator,
including automatic filing of complete readings as disruptions.

No test reaches a real model: the adapter dependency is replaced by NoModelAdapter (or a MockAdapter).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.main import app
from app.services import ai as ai_service
from app.services import whatsapp as whatsapp_service
from app.services.whatsapp import ACKNOWLEDGEMENT, auto_report_enabled
from scdc.ai.adapter import MockAdapter, NoModelAdapter

from .conftest import DEMO_MESSAGE

MAJU = "whatsapp:maju-rental (synthetic)"
API = "/api/v1"


@pytest.fixture(autouse=True)
def no_model():
    """Every request uses NoModelAdapter unless a test sets its own adapter."""
    app.dependency_overrides[ai_service.get_ai_adapter] = NoModelAdapter
    yield
    app.dependency_overrides.pop(ai_service.get_ai_adapter, None)


@pytest.fixture(autouse=True)
def auto_report():
    """Auto-report is on (the default) unless a test switches it off with `manual`."""
    app.dependency_overrides[auto_report_enabled] = lambda: True
    yield
    app.dependency_overrides.pop(auto_report_enabled, None)


@pytest.fixture
def manual():
    """SCDC_WHATSAPP_AUTO_REPORT=false: every message waits in the inbox for the owner."""
    app.dependency_overrides[auto_report_enabled] = lambda: False


@pytest.fixture(autouse=True)
def demo_clock(monkeypatch):
    """Freeze the report time at the demo's: Tuesday 20 Oct 2026, 10:15 Malaysia time."""
    monkeypatch.setattr(whatsapp_service, "report_time", lambda: datetime(2026, 10, 20, 10, 15, tzinfo=ai_service.MALAYSIA))


def send(client, **message):
    """Post one message to the inbox as the simulator would."""
    return client.post(f"{API}/whatsapp/messages", json=message)


# --- POST /whatsapp/messages --------------------------------------------------------


def test_message_from_maju_is_read_stored_and_acknowledged(seeded_client):
    """The demo message from Maju's contact is read like the extract endpoint reads it, kept, and acknowledged."""
    response = send(seeded_client, text=DEMO_MESSAGE, from_contact=MAJU)
    assert response.status_code == 201
    body = response.json()
    assert (body["id"], body["channel"], body["reply"]) == ("WA-001", "simulator", ACKNOWLEDGEMENT)
    assert body["received_at"] == "2026-10-20T02:15:00Z"   # stored as UTC, like every time in the backend
    draft = body["extraction"]["draft_incident"]
    assert (draft["supplier_id"], draft["resource_id"], draft["delivery_id"]) == ("S-01", "R-01", "DL-01")
    assert (draft["quantity_affected"], draft["new_arrival_date"]) == (20, "2026-10-23")


def test_saved_contact_name_identifies_the_supplier(seeded_client):
    """The name the owner saved for the number ("Maju") identifies the supplier when no contact reference is sent."""
    body = send(seeded_client, text=DEMO_MESSAGE, from_number="+60 12-345 6789", contact_name="Maju").json()
    assert body["extraction"]["draft_incident"]["supplier_id"] == "S-01"
    assert (body["from_number"], body["contact_name"]) == ("+60 12-345 6789", "Maju")


def test_unknown_sender_leaves_supplier_for_the_owner(seeded_client):
    """An unknown number with no saved name gives no supplier: the field stays blank and is flagged."""
    body = send(seeded_client, text=DEMO_MESSAGE, from_number="+60 19-999 0000").json()
    assert body["extraction"]["draft_incident"]["supplier_id"] is None
    assert body["extraction"]["needs_clarification"] is True


def test_empty_message_is_refused(seeded_client):
    """A message with no text is rejected and nothing is stored."""
    assert send(seeded_client, text="").status_code == 422
    assert seeded_client.get(f"{API}/whatsapp/inbox").json()["items"] == []


def test_with_auto_report_off_nothing_is_filed(seeded_client, manual):
    """With the setting off, even a complete reading only waits in the inbox."""
    body = send(seeded_client, text=DEMO_MESSAGE, from_contact=MAJU).json()
    assert (body["disruption_id"], body["report_outcome"]) == (None, None)
    assert seeded_client.get(f"{API}/disruptions").json()["items"] == []


def test_reply_never_carries_model_text(seeded_client):
    """Even when a model reads the message, the sender only gets the fixed acknowledgement."""
    adapter = MockAdapter({"*": "this is not JSON"})
    app.dependency_overrides[ai_service.get_ai_adapter] = lambda: adapter
    body = send(seeded_client, text=DEMO_MESSAGE, from_contact=MAJU).json()
    assert len(adapter.calls) == 1
    assert body["reply"] == ACKNOWLEDGEMENT
    assert body["extraction"]["fallback_used"] is True


# --- GET /whatsapp/inbox ------------------------------------------------------------


def test_inbox_lists_newest_first_with_the_stored_reading(seeded_client, manual):
    """The inbox shows every message newest first, with the reading made on arrival (as UTC)."""
    first = send(seeded_client, text=DEMO_MESSAGE, from_contact=MAJU).json()
    send(seeded_client, text="Lorry broke down, tables late", contact_name="Cahaya")
    items = seeded_client.get(f"{API}/whatsapp/inbox").json()["items"]
    assert [item["id"] for item in items] == ["WA-002", "WA-001"]
    assert items[1] == first


def test_inbox_does_not_read_messages_again(seeded_client, manual):
    """Listing the inbox never calls the model; the reading was stored when the message arrived."""
    send(seeded_client, text=DEMO_MESSAGE, from_contact=MAJU)
    adapter = MockAdapter({"*": "{}"})
    app.dependency_overrides[ai_service.get_ai_adapter] = lambda: adapter
    seeded_client.get(f"{API}/whatsapp/inbox")
    assert adapter.calls == []


# --- automatic filing -----------------------------------------------------------------


def test_complete_reading_is_filed_and_analyzed(seeded_client):
    """The demo message from Maju is complete, so it becomes D-001 at once, already analyzed, kept as a message report."""
    body = send(seeded_client, text=DEMO_MESSAGE, from_contact=MAJU).json()
    assert (body["disruption_id"], body["report_outcome"]) == ("D-001", "filed")
    disruption = seeded_client.get(f"{API}/disruptions/D-001").json()
    assert (disruption["source"], disruption["raw_message"], disruption["status"]) == ("message", DEMO_MESSAGE, "analyzed")
    incident = disruption["incident"]
    assert (incident["supplier_id"], incident["resource_id"], incident["delivery_id"]) == ("S-01", "R-01", "DL-01")
    assert (incident["quantity_affected"], incident["new_arrival_date"]) == (20, "2026-10-23")


def test_log_says_the_report_was_filed_automatically(seeded_client):
    """The activity log records which WhatsApp message filed the report, and that no person did."""
    send(seeded_client, text=DEMO_MESSAGE, from_contact=MAJU)
    log = seeded_client.get(f"{API}/disruptions/D-001/activity-log").json()["items"]
    extracted = [entry for entry in log if entry["activity_type"] == "disruption_extracted"]
    assert len(extracted) == 1
    assert extracted[0]["actor_id"] == "system"
    assert extracted[0]["details"] == {"message_id": "WA-001", "channel": "simulator", "filed_automatically": True}


def test_incomplete_reading_waits_for_the_owner(seeded_client):
    """Without the sender the supplier is unknown, so nothing is filed: the owner checks it in the form."""
    body = send(seeded_client, text=DEMO_MESSAGE).json()
    assert (body["disruption_id"], body["report_outcome"]) == (None, None)
    assert seeded_client.get(f"{API}/disruptions").json()["items"] == []


def test_message_that_is_not_a_problem_is_not_filed(seeded_client):
    """A friendly note from a known supplier has no item, quantity or date, so it is never filed."""
    body = send(seeded_client, text="Ok boss, thank you!", from_contact=MAJU).json()
    assert body["disruption_id"] is None
    assert seeded_client.get(f"{API}/disruptions").json()["items"] == []


def test_same_message_twice_links_to_the_open_report(seeded_client):
    """A repeat of an open report creates nothing new: the message is linked to D-001 and the log says so."""
    send(seeded_client, text=DEMO_MESSAGE, from_contact=MAJU)
    body = send(seeded_client, text=DEMO_MESSAGE, from_contact=MAJU).json()
    assert (body["disruption_id"], body["report_outcome"]) == ("D-001", "duplicate")
    assert [d["id"] for d in seeded_client.get(f"{API}/disruptions").json()["items"]] == ["D-001"]
    log = seeded_client.get(f"{API}/disruptions/D-001/activity-log").json()["items"]
    assert [e["details"].get("duplicate") for e in log if e["activity_type"] == "disruption_extracted"] == [None, True]


def test_inbox_shows_which_report_a_message_became(seeded_client):
    """The inbox carries the link, so the simulator can show "Reported as D-001"."""
    send(seeded_client, text=DEMO_MESSAGE, from_contact=MAJU)
    item = seeded_client.get(f"{API}/whatsapp/inbox").json()["items"][0]
    assert (item["disruption_id"], item["report_outcome"]) == ("D-001", "filed")


def test_setting_values(monkeypatch):
    """SCDC_WHATSAPP_AUTO_REPORT is on unless set to false / 0 / no / off."""
    for value, expected in [("", True), ("true", True), ("false", False), ("0", False), ("Off", False), ("no", False)]:
        monkeypatch.setenv("SCDC_WHATSAPP_AUTO_REPORT", value)
        assert auto_report_enabled() is expected, value
