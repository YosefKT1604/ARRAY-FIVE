"""Tests for draft_messages() (Module C): the model's polish is used only if it passes every check."""

from __future__ import annotations

import json

import pytest

from scdc.ai.adapter import MockAdapter, ModelTimeoutError
from scdc.ai.drafts import DraftNotAllowedError, draft_messages
from scdc.ai.drafts_template import template_drafts

GOOD_POLISH = ("Hi Cahaya Event Rentals,\n\nWe'd like to rent 20 folding chairs, delivered on 21 Oct 2026 to "
               "[DELIVERY_ADDRESS]. We estimate the order at RM 80.00 in total. Could you confirm availability "
               "and the final price?\n\nThank you,\n[YOUR_NAME]\nSeri Kenanga Events (fictional)")


def approved(plans, plan_id):
    """A copy of a demo plan, marked approved by the owner."""
    plan = next(p for p in plans if p.id == plan_id).model_copy(deep=True)
    plan.status = "approved"
    return plan


def run(reply, plan, incident, snapshot):
    """draft_messages() with a MockAdapter giving `reply`; returns the drafts and the adapter."""
    adapter = MockAdapter({"draft_message": reply})
    return draft_messages(plan, incident, snapshot, adapter=adapter), adapter


# --- Approval and fallback -------------------------------------------------------------------


def test_unapproved_plan_is_refused(plans, incident, snapshot):
    """Drafts are only made for approved plans."""
    with pytest.raises(DraftNotAllowedError):
        draft_messages(plans[0], incident, snapshot)


def test_no_adapter_gives_the_template(plans, incident, snapshot):
    """adapter=None: the template drafts, unchanged."""
    plan = approved(plans, "RP-001")
    assert draft_messages(plan, incident, snapshot) == template_drafts(plan, incident, snapshot)


@pytest.mark.parametrize("reply", [ModelTimeoutError(), "Sure, here it is!", {"body": "x", "send_now": True}])
def test_model_failures_keep_the_template(plans, incident, snapshot, reply):
    """Timeout, text that is not JSON, or a reply with extra keys: the template draft is kept."""
    plan = approved(plans, "RP-001")
    drafts, _ = run(reply, plan, incident, snapshot)
    assert drafts == template_drafts(plan, incident, snapshot)


# --- Polish used ------------------------------------------------------------------------------


def test_good_polish_is_used(plans, incident, snapshot):
    """A polish that keeps placeholders and facts and still asks: used, marked as model text."""
    drafts, adapter = run({"body": GOOD_POLISH}, approved(plans, "RP-001"), incident, snapshot)
    assert drafts[0].body == GOOD_POLISH and drafts[0].generated_by == "model:mock"
    assert drafts[0].placeholders == ["DELIVERY_ADDRESS", "YOUR_NAME"] and drafts[0].status == "draft"
    assert len(adapter.calls) == 1


def test_model_sees_only_the_draft(plans, incident, snapshot):
    """Privacy: the request has the draft text, recipient type and placeholders; no record IDs or records."""
    _, adapter = run({"body": GOOD_POLISH}, approved(plans, "RP-001"), incident, snapshot)
    request = adapter.calls[0]
    assert set(json.loads(request.user)) == {"recipient_type", "draft", "placeholders"}
    assert "S-02" not in request.user and "contact_reference" not in request.user
    assert request.task == "draft_message" and request.fixture_key == "RP-001/DM-001"


# --- Polish rejected ----------------------------------------------------------------------------


@pytest.mark.parametrize("change, why", [
    (("to [DELIVERY_ADDRESS]", "to your venue"), "placeholder dropped"),
    (("[YOUR_NAME]", "[YOUR_NAME] [DISCOUNT_CODE]"), "new placeholder"),
    (("20 folding chairs", "40 folding chairs"), "number changed"),
    (("21 Oct 2026", "22 Oct 2026"), "date changed"),
    (("RM 80.00", "RM 75.00"), "amount changed"),
    (("Hi Cahaya Event Rentals", "Hi Bintang Rentals"), "name changed"),
    (("Could you confirm availability and the final price?", "Your order is confirmed."), "question turned into a commitment"),
    (("in total.", "in total, guaranteed."), "over-claim"),
])
def test_bad_polish_keeps_the_template(plans, incident, snapshot, change, why):
    """Each kind of unsafe change makes the draft fall back to the template text."""
    plan = approved(plans, "RP-001")
    drafts, _ = run({"body": GOOD_POLISH.replace(*change)}, plan, incident, snapshot)
    assert drafts == template_drafts(plan, incident, snapshot), why


def test_request_to_maju_must_stay_a_question(plans, incident, snapshot):
    """RP-003: turning 'Could you please deliver...?' into an instruction is rejected."""
    plan = approved(plans, "RP-003")
    [template] = template_drafts(plan, incident, snapshot)
    statement = template.body.replace("Could you please deliver remaining 20 chairs by 21 Oct?",
                                      "Please deliver the remaining 20 chairs by 21 Oct.").replace(
                                      "Please let us know whether this is possible.", "")
    drafts, _ = run({"body": statement}, plan, incident, snapshot)
    assert drafts[0].body == template.body and drafts[0].generated_by == "template"
