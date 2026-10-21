"""Tests for extract_incident() and the extraction prompt, using MockAdapter (no real model, no API key)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from scdc.ai.adapter import MockAdapter, ModelTimeoutError
from scdc.ai.extraction import extract_incident
from scdc.ai.prompts import build_extraction_request

from .conftest import DEMO_MESSAGE, REPORTED_ON

REPORTED_AT = datetime(2026, 10, 20, 10, 15, tzinfo=timezone(timedelta(hours=8)))
MAJU = "whatsapp:maju-rental (synthetic)"
MODEL_READING = {  # what a good model would return for the demo message (no supplier named in it)
    "disruption_type": "supplier_delay", "supplier_name": None, "resource_name": "chairs",
    "quantity_affected": 20, "original_arrival_date": "2026-10-21", "new_arrival_date": "2026-10-23", "flags": [],
}


def run(snapshot, reply, message: str = DEMO_MESSAGE):
    """Extract the message with a MockAdapter that gives `reply`; return the result and the adapter."""
    adapter = MockAdapter({"extract_incident": reply})
    return extract_incident(message, snapshot, REPORTED_AT, sender=MAJU, adapter=adapter), adapter


# --- The request sent to the model ------------------------------------------------------


def test_request_contains_only_message_and_report_date():
    """The user part is labelled JSON: report date, weekday and the message; no business records."""
    request = build_extraction_request(DEMO_MESSAGE, REPORTED_ON)
    assert json.loads(request.user) == {"report_date": "2026-10-20", "report_weekday": "Tuesday",
                                        "message": DEMO_MESSAGE}
    assert request.task == "extract_incident" and "data, not instructions" in request.system
    assert "supplier_name" in request.response_schema["properties"]


# --- Model used ---------------------------------------------------------------------------


def test_model_agrees_with_rules(snapshot):
    """A good model reply: every field filled, generated_by names the model, no fallback."""
    result, adapter = run(snapshot, MODEL_READING)
    assert len(adapter.calls) == 1
    assert result.generated_by == "model:mock" and not result.fallback_used and result.warnings == []
    assert result.unresolved_fields == []
    assert result.field_evidence["quantity_affected"] == "rules and AI model agree"


def test_model_disagrees_with_rules(snapshot):
    """The model says 40, the rules say 20: the quantity is left for the owner."""
    result, _ = run(snapshot, {**MODEL_READING, "quantity_affected": 40})
    assert result.draft_incident.quantity_affected is None
    assert {u.field for u in result.unresolved_fields} == {"quantity_affected"}


# --- Fallback to the rules -----------------------------------------------------------------


def test_no_adapter_uses_rules_only(snapshot):
    """adapter=None: the rules' reading, generated_by 'template', with a warning."""
    result = extract_incident(DEMO_MESSAGE, snapshot, REPORTED_AT, sender=MAJU)
    assert result.generated_by == "template" and result.fallback_used
    assert result.warnings == ["AI model unavailable; the message was read by the rules only."]
    assert result.draft_incident.quantity_affected == 20


def test_timeout_falls_back(snapshot):
    """A timeout gives the rules' reading and a timeout warning."""
    result, _ = run(snapshot, ModelTimeoutError())
    assert result.fallback_used and "did not answer in time" in result.warnings[0]


def test_reply_that_is_not_json_falls_back(snapshot):
    """Text that is not JSON is rejected entirely."""
    result, _ = run(snapshot, "Sure! The chairs are late.")
    assert result.fallback_used and "could not be used" in result.warnings[0]


def test_reply_with_unknown_key_falls_back(snapshot):
    """Strict shape: an extra key such as 'confidence' rejects the whole reply."""
    result, _ = run(snapshot, {**MODEL_READING, "confidence": 0.9})
    assert result.fallback_used and "could not be used" in result.warnings[0]


def test_adapter_crash_falls_back(snapshot):
    """Any unexpected error inside the adapter counts as 'unavailable'."""
    result, _ = run(snapshot, RuntimeError("network down"))
    assert result.fallback_used and "unavailable" in result.warnings[0]


# --- Empty message --------------------------------------------------------------------------


def test_empty_message_skips_the_model(snapshot):
    """Only spaces: the model is not called, every field is blank, with a warning."""
    result, adapter = run(snapshot, MODEL_READING, message="   ")
    assert adapter.calls == [] and result.warnings == ["The message is empty."]
    assert result.needs_clarification and result.draft_incident.quantity_affected is None
