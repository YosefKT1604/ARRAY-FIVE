"""Tests for explain() (Module B): model text where it passes the claim check, template everywhere else."""

from __future__ import annotations

import json

from scdc.ai.adapter import MockAdapter, ModelTimeoutError
from scdc.ai.explanation import explain
from scdc.ai.explanation_template import template_explanation

GOOD_REPLY = {  # what a careful model might write for the demo; it leaves some items out on purpose
    "summary": ("Maju Rental Supplies will send only 20 of the 40 chairs tomorrow; the other 20 arrive on Friday. "
                "Two jobs on Thursday, J-01 and J-02, are now short of chairs. RP-001 is the only feasible plan."),
    "impact_explanations": [
        {"entity_id": "J-01", "text": "The wedding on Thursday needs 50 chairs, but the shared pool is short by 20 that day."},
    ],
    "plan_comparisons": [
        {"plan_id": "RP-001",
         "benefits": [{"source": "cost", "text": "Costs RM 80.00."},
                      {"source": "DEADLINE_MET", "text": "The chairs arrive before the events on Thursday."}]},
        {"plan_id": "RP-002",
         "limitations": [{"source": "DEADLINE_MET", "text": "Delima's chairs would only arrive on Friday, after the events."}]},
    ],
}


def run(reply, incident, impact, plans, snapshot):
    """explain() with a MockAdapter giving `reply`; returns the explanation and the adapter."""
    adapter = MockAdapter({"explain": reply})
    return explain(incident, impact, plans, snapshot=snapshot, adapter=adapter), adapter


def comparison(explanation, plan_id):
    """The PlanComparison for one plan."""
    return next(c for c in explanation.plan_comparisons if c.plan_id == plan_id)


def with_plan(reply, plan_id, **lists):
    """A copy of a reply with one plan's benefits/limitations replaced."""
    copy = json.loads(json.dumps(reply))
    copy["plan_comparisons"] = [c for c in copy["plan_comparisons"] if c["plan_id"] != plan_id]
    copy["plan_comparisons"].append({"plan_id": plan_id, **lists})
    return copy


# --- No model ---------------------------------------------------------------------------------


def test_no_adapter_gives_the_template(incident, impact, plans, snapshot):
    """adapter=None: exactly the template explanation."""
    result = explain(incident, impact, plans, snapshot=snapshot)
    assert result == template_explanation(incident, impact, plans, snapshot=snapshot)


def test_model_failures_give_the_template(incident, impact, plans, snapshot):
    """Timeout, text that is not JSON, and a reply that sets a status all fall back to the template."""
    template = template_explanation(incident, impact, plans, snapshot=snapshot)
    for reply in (ModelTimeoutError(), "Here is your explanation!",
                  {"summary": "x", "plan_comparisons": [{"plan_id": "RP-002", "validation_status": "feasible"}]}):
        result, _ = run(reply, incident, impact, plans, snapshot)
        assert result == template


# --- Model text used ----------------------------------------------------------------------------


def test_good_reply_is_used_where_given(incident, impact, plans, snapshot):
    """Passing items are the model's; items it left out come from the template; nothing is counted."""
    result, adapter = run(GOOD_REPLY, incident, impact, plans, snapshot)
    template = template_explanation(incident, impact, plans, snapshot=snapshot)
    assert result.generated_by == "model:mock" and not result.fallback_used
    assert result.unsupported_claims_removed == 0 and len(adapter.calls) == 1
    assert result.summary == GOOD_REPLY["summary"]
    assert result.impact_explanations[1].text == "Confirmed: " + GOOD_REPLY["impact_explanations"][0]["text"]
    assert result.impact_explanations[2] == template.impact_explanations[2]
    rp1 = comparison(result, "RP-001")
    assert "Costs RM 80.00." in rp1.benefits and "S-02 confirmed 25 available." in rp1.benefits
    assert comparison(result, "RP-002").limitations[1] == GOOD_REPLY["plan_comparisons"][1]["limitations"][0]["text"]


def test_statuses_confirmations_and_steps_come_from_code(incident, impact, plans, snapshot):
    """Even with model text, statuses, missing confirmations and next steps are the template's."""
    result, _ = run(GOOD_REPLY, incident, impact, plans, snapshot)
    template = template_explanation(incident, impact, plans, snapshot=snapshot)
    assert [(c.plan_id, c.validation_status) for c in result.plan_comparisons] == [
        (c.plan_id, c.validation_status) for c in template.plan_comparisons]
    assert result.missing_confirmations == template.missing_confirmations
    assert result.next_steps == template.next_steps


# --- Unsupported and invented items ------------------------------------------------------------------


def test_unsupported_item_is_replaced(incident, impact, plans, snapshot):
    """Calling infeasible RP-002 'a good option' replaces that item with the template's, and counts it."""
    reply = with_plan(GOOD_REPLY, "RP-002", benefits=[{"source": "cost", "text": "A good option at RM 56.00."}])
    result, _ = run(reply, incident, impact, plans, snapshot)
    assert "Estimated cost: RM 56.00." in comparison(result, "RP-002").benefits
    assert result.unsupported_claims_removed == 1 and result.generated_by == "model:mock"


def test_wrong_number_in_an_impact_text_is_replaced(incident, impact, plans, snapshot):
    """'short by 25' is not in the data: the template text is used instead."""
    reply = {**GOOD_REPLY, "impact_explanations": [{"entity_id": "J-01", "text": "The wedding is short by 25 chairs."}]}
    result, _ = run(reply, incident, impact, plans, snapshot)
    template = template_explanation(incident, impact, plans, snapshot=snapshot)
    assert result.impact_explanations[1] == template.impact_explanations[1]
    assert result.unsupported_claims_removed == 1


def test_invented_records_and_keys_are_dropped(incident, impact, plans, snapshot):
    """An unknown record, an unknown plan and an unknown key are dropped, and each is counted."""
    reply = with_plan(GOOD_REPLY, "RP-001", benefits=[{"source": "SPEED", "text": "Very fast."}])
    reply["impact_explanations"] = [{"entity_id": "J-09", "text": "Also affected."}]
    reply["plan_comparisons"].append({"plan_id": "RP-009", "benefits": [{"source": "cost", "text": "Free."}]})
    result, _ = run(reply, incident, impact, plans, snapshot)
    assert result.unsupported_claims_removed == 3
    assert "J-09" not in [i.entity_id for i in result.impact_explanations]
    assert "RP-009" not in [c.plan_id for c in result.plan_comparisons]
    assert "Very fast." not in comparison(result, "RP-001").benefits


def test_nothing_survives_reports_template(incident, impact, plans, snapshot):
    """If no model text passes, the result is labelled as the template (not AI-generated)."""
    result, _ = run({"summary": "Delivery is guaranteed for every event."}, incident, impact, plans, snapshot)
    assert result.generated_by == "template" and result.fallback_used
    assert result.unsupported_claims_removed == 1
    assert result.summary == template_explanation(incident, impact, plans, snapshot=snapshot).summary


# --- What the model is given --------------------------------------------------------------------------


def test_facts_sent_to_the_model(incident, impact, plans, snapshot):
    """FACTS include statuses, the keys to write, record names; no template text."""
    _, adapter = run(GOOD_REPLY, incident, impact, plans, snapshot)
    request = adapter.calls[0]
    facts = json.loads(request.user)["FACTS"]
    rp2 = next(p for p in facts["plans"] if p["plan_id"] == "RP-002")
    assert rp2["validation_status"] == "infeasible" and rp2["estimated_cost"] == "RM 56.00"
    assert rp2["benefit_keys"] == ["SUPPLIER_AVAILABLE", "cost"]
    assert rp2["limitation_keys"] == ["LEAD_TIME_OK", "DEADLINE_MET"]
    assert facts["names"]["S-02"] == "Cahaya Event Rentals (S-02)" and facts["report_weekday"] == "Tuesday"
    assert "Estimated cost:" not in request.user and "severity" not in request.user
    assert request.task == "explain" and "validation_status is final" in request.system
