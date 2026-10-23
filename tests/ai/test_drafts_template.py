"""Tests for the template draft messages (Module C's deterministic part), on the demo plans."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from scdc.ai.drafts_template import long_date, placeholders_in, template_drafts
from scdc.ai.schemas import DraftMessage, RawDraft, RecoveryAction


def plan(plans, plan_id):
    """One demo plan by ID."""
    return next(p for p in plans if p.id == plan_id)


def action(action_type, **parameters):
    """A recovery action of the given type, for building test plans."""
    return RecoveryAction(id="RA-9", action_type=action_type, parameters=parameters, status="draft",
                          target_entity={"entity_type": "job", "entity_id": parameters.get("job_id", "R-01")})


def test_order_request_to_the_new_supplier(plans, incident, snapshot):
    """RP-001: one draft to Cahaya with the items, date, cost estimate and an address placeholder."""
    [draft] = template_drafts(plan(plans, "RP-001"), incident, snapshot)
    assert (draft.id, draft.plan_id, draft.recipient_type.value, draft.recipient_id) == ("DM-001", "RP-001", "supplier", "S-02")
    assert draft.body.startswith("Hi Cahaya Event Rentals,")
    assert "rent 20 folding chairs for delivery on 21 Oct 2026 to [DELIVERY_ADDRESS]" in draft.body
    assert "RM 80.00" in draft.body and "confirm the availability" in draft.body
    assert draft.placeholders == ["DELIVERY_ADDRESS", "YOUR_NAME"]
    assert draft.status == "draft" and draft.generated_by == "template"


def test_supplier_request_is_a_question(plans, incident, snapshot):
    """RP-003: Maju is asked, not told; the date in the request is not repeated."""
    [draft] = template_drafts(plan(plans, "RP-003"), incident, snapshot)
    assert draft.recipient_id == "S-01" and draft.body.startswith("Hi Maju Rental Supplies,")
    assert "will now arrive on 23 Oct 2026" in draft.body
    assert "Could you please deliver remaining 20 chairs by 21 Oct?" in draft.body
    assert "We would need them by" not in draft.body and "whether this is possible" in draft.body


def test_requested_date_is_added_when_missing_from_the_request(plans, incident, snapshot):
    """A request without a date gets the requested date as a separate sentence."""
    p = plan(plans, "RP-003").model_copy(deep=True)
    p.actions[0].parameters["request"] = "Send the remaining chairs earlier"
    [draft] = template_drafts(p, incident, snapshot)
    assert "Could you please send the remaining chairs earlier? We would need them by 21 Oct 2026." in draft.body


def test_reschedule_proposes_never_promises(plans, incident, snapshot):
    """A reschedule action gives a customer draft that asks whether the new date works."""
    p = plan(plans, "RP-001").model_copy(deep=True)
    p.actions = [action("reschedule_job", job_id="J-03", new_date="2026-10-26")]
    [draft] = template_drafts(p, incident, snapshot)
    assert (draft.recipient_type.value, draft.recipient_id) == ("customer", "C-03")
    assert "Birthday party, Taman Melawati on 25 Oct 2026" in draft.body
    assert "whether 26 Oct 2026 would work for you" in draft.body
    assert draft.placeholders == ["CUSTOMER_NAME", "YOUR_NAME"]


def test_internal_actions_give_no_message(plans, incident, snapshot):
    """Using spare stock or moving items between jobs needs no outside message."""
    p = plan(plans, "RP-001").model_copy(deep=True)
    p.actions = [action("use_spare_inventory", resource_id="R-01", quantity=5),
                 action("reallocate_resource", resource_id="R-01", quantity=5, from_job_id="J-03", to_job_id="J-01")]
    assert template_drafts(p, incident, snapshot) == []


def test_unknown_records_become_placeholders(plans, incident, snapshot):
    """A supplier or item missing from the data becomes a placeholder, listed for the owner."""
    p = plan(plans, "RP-001").model_copy(deep=True)
    p.actions[0].parameters.update(supplier_id="S-99", resource_id="R-99")
    [draft] = template_drafts(p, incident, snapshot)
    assert draft.body.startswith("Hi [SUPPLIER_NAME],") and "20 [ITEM_NAME]" in draft.body
    assert draft.placeholders == ["SUPPLIER_NAME", "ITEM_NAME", "DELIVERY_ADDRESS", "YOUR_NAME"]


def test_several_actions_are_numbered(plans, incident, snapshot):
    """Two outside-facing actions give DM-001 and DM-002; the cost estimate is left out for multi-action plans."""
    p = plan(plans, "RP-001").model_copy(deep=True)
    p.actions.append(action("reschedule_job", job_id="J-03", new_date="2026-10-26"))
    drafts = template_drafts(p, incident, snapshot)
    assert [d.id for d in drafts] == ["DM-001", "DM-002"]
    assert "RM 80.00" not in drafts[0].body


def test_helpers():
    """Dates read like '21 Oct 2026'; placeholders are listed once, without brackets."""
    assert long_date("2026-10-21") == "21 Oct 2026" and long_date(None) == "[DATE]"
    assert placeholders_in("[A_B] x [C] y [A_B] z [lower]") == ["A_B", "C"]


def test_draft_shapes_are_strict():
    """DraftMessage only allows draft/approved; the model's reply is a non-empty body and nothing else."""
    with pytest.raises(ValidationError):
        DraftMessage(id="DM-001", plan_id="RP-001", recipient_type="supplier", recipient_id="S-02",
                     body="x", status="sent", generated_by="template")
    assert RawDraft.model_validate({"body": "Hello"}).body == "Hello"
    with pytest.raises(ValidationError):
        RawDraft.model_validate({"body": "Hello", "send_now": True})
    with pytest.raises(ValidationError):
        RawDraft.model_validate({"body": ""})
