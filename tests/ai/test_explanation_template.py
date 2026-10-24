"""Tests for the template explanation (Module B's deterministic part), on the demo data."""

from __future__ import annotations

import re

from scdc.ai.explanation_template import build_template, fmt_date, template_explanation
from scdc.ai.schemas import ImpactStatus


def comparison(explanation, plan_id):
    """The PlanComparison for one plan."""
    return next(c for c in explanation.plan_comparisons if c.plan_id == plan_id)


def test_demo_summary_with_names(incident, impact, plans, snapshot):
    """With business names the summary is plain sentences: names, weekday dates, no IDs, no record counts."""
    text = template_explanation(incident, impact, plans, snapshot=snapshot).summary
    assert text == (
        "20 folding chairs from Maju Rental Supplies will arrive 2 days late (Fri 23 Oct instead of Wed 21 Oct). "
        "This hits the Aisyah & Daniel wedding reception and the Tekno Solutions product seminar on Thu 22 Oct: "
        "short 20 chairs. Not affected: Birthday party, Taman Melawati (Sun 25 Oct). "
        "Best option: rent 20 chairs from Cahaya Event Rentals for delivery on Wed 21 Oct (RM 80)."
    )
    assert not re.search(r"\b[A-Z]{1,3}-\d{2,4}\b|record\(s\)|plan\(s\)|\d{4}-\d{2}-\d{2}", text)


def test_plain_summary_without_a_feasible_plan(incident, impact, plans, snapshot):
    """No feasible plan: the summary says so and offers no best option."""
    text = template_explanation(incident, impact, plans[1:], snapshot=snapshot).summary
    assert "Best option" not in text and "None of the 2 options we checked is confirmed to work yet." in text


def test_without_snapshot_ids_are_used(incident, impact, plans):
    """No business data: records are shown by ID only."""
    explanation = template_explanation(incident, impact, plans)
    assert explanation.summary.startswith("S-01 will deliver 20 units of R-01 late")
    assert explanation.impact_explanations[1].text.startswith("Confirmed: J-01: ")


def test_impact_texts_carry_the_status_and_p3_reason(incident, impact, plans, snapshot):
    """One text per affected record, starting with its status, using P3's reason."""
    texts = template_explanation(incident, impact, plans, snapshot=snapshot).impact_explanations
    assert [t.entity_id for t in texts] == ["R-01", "J-01", "J-02", "CM-01", "CM-02"]
    assert texts[1].text == ("Confirmed: Aisyah & Daniel wedding reception (J-01): "
                             "Shared chair pool short by 20 on 2026-10-22; J-01 requires 50.")


def test_potential_risk_label(incident, impact, plans):
    """A different impact status gives a different label; the label always comes from the data."""
    impact.affected_entities[1].impact_status = ImpactStatus.POTENTIAL_RISK
    texts = template_explanation(incident, impact, plans).impact_explanations
    assert texts[1].text.startswith("Possible risk: ")


def test_plan_statuses_are_copied_and_ordered(incident, impact, plans):
    """Ranked plan first, then needs confirmation, then infeasible; statuses copied from P4."""
    comparisons = template_explanation(incident, impact, plans).plan_comparisons
    assert [(c.plan_id, c.validation_status.value) for c in comparisons] == [
        ("RP-001", "feasible"), ("RP-003", "needs_confirmation"), ("RP-002", "infeasible")]


def test_benefits_and_limitations_come_from_checks(incident, impact, plans):
    """Passed checks and cost are benefits; failed / unresolved checks and assumptions are limitations."""
    explanation = template_explanation(incident, impact, plans)
    rp2, rp3 = comparison(explanation, "RP-002"), comparison(explanation, "RP-003")
    assert rp2.benefits == ["S-03 confirmed 60 available.", "Estimated cost: RM 56.00."]
    assert rp2.limitations == ["Fails: 3-day lead time; earliest arrival 2026-10-23.",
                               "Fails: 2026-10-23 is after 2026-10-22."]
    assert rp3.limitations[-1] == "Assumes: S-01 can expedite the remaining 20 chairs to 2026-10-21."


def test_items_are_keyed_by_source(incident, impact, plans):
    """The keyed template items use the approved keys: check codes, assumption:N, cost."""
    raw = build_template(incident, impact, plans).raw
    keys = {c.plan_id: ([b.source for b in c.benefits], [x.source for x in c.limitations]) for c in raw.plan_comparisons}
    assert keys["RP-002"] == (["SUPPLIER_AVAILABLE", "cost"], ["LEAD_TIME_OK", "DEADLINE_MET"])
    assert keys["RP-003"] == ([], ["SUPPLIER_AVAILABLE", "FACTS_KNOWN", "assumption:1"])


def test_unvalidated_plan_is_flagged(incident, impact, plans):
    """A plan without a ValidationResult has no status and says so."""
    plans[0].validation = None
    explanation = template_explanation(incident, impact, plans)
    rp1 = comparison(explanation, "RP-001")
    assert rp1.validation_status is None and rp1.limitations == ["This plan has not been validated yet."]
    assert any("Validate RP-001" in s for s in explanation.next_steps)


def test_missing_confirmations_and_next_steps(incident, impact, plans):
    """Only the feasible plan is offered for approval; RP-003's assumption must be confirmed."""
    explanation = template_explanation(incident, impact, plans)
    assert explanation.missing_confirmations == [
        "RP-003: confirm that S-01 can expedite the remaining 20 chairs to 2026-10-21."]
    assert explanation.next_steps[0] == "Review RP-001 and approve or reject it."
    assert not any("RP-002" in s and "approve" in s for s in explanation.next_steps)


def test_no_feasible_plan(incident, impact, plans):
    """Without a feasible plan, nothing is offered for approval."""
    explanation = template_explanation(incident, impact, plans[1:])
    assert explanation.next_steps[0].startswith("No plan is feasible yet")
    assert "feasible: none" in explanation.summary


def test_shortfall_summary(incident, impact, plans):
    """A shortfall says the items cannot be supplied."""
    incident.type = "supplier_shortfall"
    assert "cannot supply 20 units of R-01" in template_explanation(incident, impact, plans).summary


def test_template_provenance_and_dates(incident, impact, plans):
    """Template output is marked as such; dates are short English dates."""
    explanation = template_explanation(incident, impact, plans)
    assert explanation.generated_by == "template" and explanation.fallback_used
    assert explanation.unsupported_claims_removed == 0 and explanation.disruption_id == "D-001"
    assert fmt_date(incident.new_arrival_date) == "23 Oct"
