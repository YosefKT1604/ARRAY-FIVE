"""Tests for the claim checker (Module B), on the demo data."""

from __future__ import annotations

import pytest

from scdc.ai.claims import CheckContext, facts_for_impact, facts_for_plan, facts_for_summary, find_problems
from scdc.ai.explanation_template import build_template


def plan(plans, plan_id):
    """One plan by ID."""
    return next(p for p in plans if p.id == plan_id)


def statuses(plans):
    """Plan ID -> validation status."""
    return {p.id: p.validation.status for p in plans}


def check_plan_text(text, plan_id, incident, impact, plans, snapshot=None):
    """Problems in a benefit or limitation written for one plan."""
    facts = facts_for_plan(plan(plans, plan_id), incident, impact, snapshot)
    context = CheckContext(incident.reported_at.date(), incident.original_arrival_date, statuses(plans), plan_id)
    return find_problems(text, facts, context)


def check_summary(text, incident, impact, plans, snapshot=None):
    """Problems in a summary text."""
    facts = facts_for_summary(incident, impact, plans, snapshot)
    return find_problems(text, facts, CheckContext(incident.reported_at.date(), incident.original_arrival_date,
                                                   statuses(plans)))


def check_impact_text(text, entity_id, incident, impact, snapshot=None):
    """Problems in the text for one affected record."""
    entity = next(e for e in impact.affected_entities if e.entity_id == entity_id)
    facts = facts_for_impact(entity, incident, impact, snapshot)
    return find_problems(text, facts, CheckContext(incident.reported_at.date(), incident.original_arrival_date,
                                                   affected=True))


# --- The template passes its own check ---------------------------------------------------------


@pytest.mark.parametrize("with_names", [True, False])
def test_every_template_item_is_supported(incident, impact, plans, snapshot, with_names):
    """Everything the template writes is backed by the data, with or without business names."""
    snap = snapshot if with_names else None
    raw = build_template(incident, impact, plans, snapshot=snap).raw
    assert check_summary(raw.summary, incident, impact, plans, snap) == []
    for item in raw.impact_explanations:
        assert check_impact_text(item.text, item.entity_id, incident, impact, snap) == [], item.text
    for comparison in raw.plan_comparisons:
        for item in comparison.benefits + comparison.limitations:
            assert check_plan_text(item.text, comparison.plan_id, incident, impact, plans, snap) == [], item.text


# --- Facts: IDs, numbers, money, dates, names ---------------------------------------------------


def test_unknown_id_and_number(incident, impact, plans):
    """An invented record and an invented quantity are both caught."""
    problems = check_plan_text("Cahaya brings 45 chairs, enough for J-09.", "RP-001", incident, impact, plans)
    assert "unknown record J-09" in problems and "number 45 not in the data" in problems


def test_number_words(incident, impact, plans):
    """'twenty' is a fact; 'forty-five' is not; 'one' is not checked."""
    assert check_plan_text("Cahaya sends twenty chairs, one day ahead.", "RP-001", incident, impact, plans) == []
    assert check_plan_text("Cahaya sends forty-five chairs.", "RP-001", incident, impact, plans) == [
        "number 45 not in the data"]


def test_money_is_scoped_to_the_plan(incident, impact, plans):
    """RM 80.00 is RP-001's cost: allowed for RP-001, not for RP-002 (whose cost is RM 56.00)."""
    assert check_plan_text("It costs RM 80.00.", "RP-001", incident, impact, plans) == []
    assert check_plan_text("It costs RM 80.00.", "RP-002", incident, impact, plans) == ["amount RM 80.00 not in the data"]


def test_dates_explicit_weekday_and_relative(incident, impact, plans):
    """'Thursday' (22 Oct) and 'tomorrow' (21 Oct) are facts; 'Saturday' (24 Oct) and 'next week' are not."""
    assert check_plan_text("Arrives tomorrow, before the events on Thursday.", "RP-001", incident, impact, plans) == []
    assert check_plan_text("Arrives on Saturday.", "RP-001", incident, impact, plans) == [
        "date 2026-10-24 ('Saturday') not in the data"]
    assert check_plan_text("Arrives next week.", "RP-001", incident, impact, plans) == ["vague date 'next week'"]


def test_days_late_uses_the_original_date(incident, impact, plans):
    """'two days late' = 21 Oct + 2 = 23 Oct (a fact); 'five days late' = 26 Oct (not)."""
    assert check_summary("The chairs will be two days late.", incident, impact, plans) == []
    assert check_summary("The chairs will be five days late.", incident, impact, plans) != []


def test_metadata_dates_do_not_count(incident, impact, plans, snapshot):
    """SO-03 was confirmed on 19 Oct, but that bookkeeping date cannot support a claim."""
    assert check_plan_text("Delima delivers on 19 Oct.", "RP-002", incident, impact, plans, snapshot) == [
        "date 2026-10-19 ('19 Oct') not in the data"]


def test_business_names(incident, impact, plans, snapshot):
    """A known supplier name is fine; an invented one is caught; a lone 'Rentals' is not a name."""
    assert check_plan_text("Ask Cahaya Event Rentals for the chairs.", "RP-001", incident, impact, plans, snapshot) == []
    assert check_plan_text("Ask Bintang Rentals for the chairs.", "RP-001", incident, impact, plans, snapshot) == [
        "unknown name 'Bintang Rentals'"]
    assert check_plan_text("Rentals are quick.", "RP-001", incident, impact, plans, snapshot) == []


# --- Status rules ----------------------------------------------------------------------------------


def test_infeasible_plan_cannot_be_praised_or_approved(incident, impact, plans):
    """RP-002 failed validation: 'good option' and 'approve' are caught; 'do not approve' is fine."""
    assert check_plan_text("This is a good option.", "RP-002", incident, impact, plans) != []
    assert check_plan_text("Approve this plan.", "RP-002", incident, impact, plans) != []
    assert check_plan_text("Do not approve this plan as it stands.", "RP-002", incident, impact, plans) == []
    assert check_plan_text("It is not feasible.", "RP-002", incident, impact, plans) == []


def test_needs_confirmation_plan_cannot_be_called_feasible(incident, impact, plans):
    """RP-003 still needs confirmation: 'feasible' and 'go ahead' are caught."""
    assert check_plan_text("This plan is feasible.", "RP-003", incident, impact, plans) != []
    assert check_plan_text("Go ahead with it.", "RP-003", incident, impact, plans) != []


def test_feasible_plan_cannot_be_called_infeasible(incident, impact, plans):
    """RP-001 is feasible: 'not feasible' and 'not yet confirmed' contradict P4."""
    assert check_plan_text("It is not feasible.", "RP-001", incident, impact, plans) != []
    assert check_plan_text("The supplier is not yet confirmed.", "RP-001", incident, impact, plans) != []


def test_summary_sentence_about_one_plan(incident, impact, plans):
    """In the summary, a sentence naming one plan is checked against that plan's status."""
    assert check_summary("RP-002 is the best option.", incident, impact, plans) != []
    assert check_summary("RP-001 is feasible.", incident, impact, plans) == []


def test_negation_must_be_in_the_same_clause(incident, impact, plans):
    """'not' before a ':' or ',' / 'but' does not negate what follows; a nearby 'not' still does."""
    assert check_summary("Do not wait: RP-003 is the best option.", incident, impact, plans) != []
    assert check_plan_text("Not cheap, but feasible.", "RP-002", incident, impact, plans) != []
    assert check_plan_text("It is not a good option.", "RP-002", incident, impact, plans) == []


def test_over_claims(incident, impact, plans):
    """'guaranteed' is never allowed; 'not guaranteed' is fine."""
    assert check_plan_text("Delivery is guaranteed.", "RP-001", incident, impact, plans) == ["over-claim 'guaranteed'"]
    assert check_plan_text("Delivery is not guaranteed.", "RP-001", incident, impact, plans) == []


def test_affected_record_cannot_be_called_unaffected(incident, impact):
    """J-01 is affected; saying it is not is a contradiction."""
    assert check_impact_text("J-01 is not affected.", "J-01", incident, impact) == [
        "says an affected record is 'not affected'"]
