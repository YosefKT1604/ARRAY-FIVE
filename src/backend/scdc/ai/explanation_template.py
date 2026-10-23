"""Module B, deterministic part: the template explanation, built only from the structured data.

It is always built. It is the fallback when no model is available, and the source of the item
that replaces any model item that fails the claim check (step 3c).

Benefits and limitations are keyed by `source` (the same keys the model must use):
    <CHECK_CODE>    a passed check (benefit), or a failed / unresolved check (limitation)
    assumption:N    the plan's Nth assumption, from 1 (limitation)
    cost            the estimated cost (benefit)
    validation      the plan has not been validated yet (limitation; code only)

Missing confirmations and next steps are written by code only; the model never changes them.
A plan's validation status is copied from Person 4's ValidationResult, never worked out here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .schemas import (
    BusinessSnapshot,
    CheckResult,
    DisruptionType,
    Explanation,
    ImpactExplanation,
    ImpactResult,
    ImpactStatus,
    Money,
    NormalizedIncident,
    PlanComparison,
    RawExplanation,
    RawItem,
    RawPlanComparison,
    RecoveryPlan,
    ValidationStatus,
)

# Shown before each impact text by code, so the model cannot change an impact's status.
IMPACT_STATUS_LABELS = {
    ImpactStatus.CONFIRMED: "Confirmed",
    ImpactStatus.POTENTIAL_RISK: "Possible risk",
    ImpactStatus.UNRESOLVED: "Not yet known",
}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
# Order used to list plans when they have no rank: usable plans first.
STATUS_ORDER = {ValidationStatus.FEASIBLE: 0, ValidationStatus.NEEDS_CONFIRMATION: 1, ValidationStatus.INFEASIBLE: 2}


@dataclass
class ExplanationTemplate:
    """The template's texts (keyed, same shape as the model's reply) plus the code-only lists."""

    raw: RawExplanation
    missing_confirmations: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)


# --- Public functions -----------------------------------------------------------------


def build_template(
    incident: NormalizedIncident,
    impact: ImpactResult,
    plans: list[RecoveryPlan],
    *,
    snapshot: BusinessSnapshot | None = None,
) -> ExplanationTemplate:
    """Write the whole explanation from the data. With a snapshot, records are shown with their names."""
    ordered = order_plans(plans)
    raw = RawExplanation(
        summary=summary(incident, impact, ordered, snapshot),
        impact_explanations=[
            ImpactExplanation(entity_id=e.entity_id, text=f"{label(e.entity_id, snapshot)}: {e.reason}")
            for e in impact.affected_entities
        ],
        plan_comparisons=[plan_items(plan) for plan in ordered],
    )
    return ExplanationTemplate(raw, missing_confirmations(incident, impact, ordered), next_steps(impact, ordered))


def assemble(
    texts: RawExplanation,
    template: ExplanationTemplate,
    impact: ImpactResult,
    plans: list[RecoveryPlan],
    *,
    generated_by: str,
    fallback_used: bool,
    unsupported_claims_removed: int = 0,
) -> Explanation:
    """Turn checked texts into the final Explanation: add impact status labels, copy plan statuses."""
    statuses = {e.entity_id: e.impact_status for e in impact.affected_entities}
    by_id = {p.id: p for p in plans}
    return Explanation(
        disruption_id=impact.disruption_id,
        summary=texts.summary,
        impact_explanations=[
            ImpactExplanation(entity_id=item.entity_id,
                              text=f"{IMPACT_STATUS_LABELS[statuses[item.entity_id]]}: {item.text}")
            for item in texts.impact_explanations
        ],
        plan_comparisons=[
            PlanComparison(
                plan_id=item.plan_id,
                validation_status=status_of(by_id[item.plan_id]),
                benefits=[b.text for b in item.benefits],
                limitations=[x.text for x in item.limitations],
            )
            for item in texts.plan_comparisons
        ],
        missing_confirmations=list(template.missing_confirmations),
        next_steps=list(template.next_steps),
        generated_by=generated_by,
        fallback_used=fallback_used,
        unsupported_claims_removed=unsupported_claims_removed,
    )


def template_explanation(
    incident: NormalizedIncident,
    impact: ImpactResult,
    plans: list[RecoveryPlan],
    *,
    snapshot: BusinessSnapshot | None = None,
) -> Explanation:
    """The explanation with no model at all (generated_by "template", fallback_used True)."""
    template = build_template(incident, impact, plans, snapshot=snapshot)
    return assemble(template.raw, template, impact, order_plans(plans), generated_by="template", fallback_used=True)


# --- Formatting helpers ------------------------------------------------------------------


def fmt_date(value: date | None) -> str:
    """A short date for the owner, e.g. "21 Oct" (English month names, whatever the computer's language)."""
    return f"{value.day} {MONTHS[value.month - 1]}" if value else "an unknown date"


def fmt_money(money: Money) -> str:
    """A money amount, e.g. "RM 80.00"."""
    prefix = "RM" if money.currency == "MYR" else money.currency
    return f"{prefix} {money.amount:.2f}"


def label(entity_id: str, snapshot: BusinessSnapshot | None) -> str:
    """A record's name followed by its ID ("Cahaya Event Rentals (S-02)"), or just the ID."""
    if snapshot is None:
        return entity_id
    for records in (snapshot.suppliers, snapshot.resources, snapshot.jobs):
        for record in records:
            if record.id == entity_id:
                return f"{record.name} ({entity_id})"
    for commitment in snapshot.commitments:
        if commitment.id == entity_id:
            return f"{label(commitment.job_id, snapshot)} customer commitment ({entity_id})"
    return entity_id


def _items_name(incident: NormalizedIncident, snapshot: BusinessSnapshot | None) -> str:
    """How to call the affected items: "folding chairs" with a snapshot, else "units of R-01"."""
    if snapshot is not None:
        resource = next((r for r in snapshot.resources if r.id == incident.resource_id), None)
        if resource is not None:
            return resource.name.lower()
    return f"units of {incident.resource_id}" if incident.resource_id else "items"


def status_of(plan: RecoveryPlan) -> ValidationStatus | None:
    """A plan's validation status as set by Person 4 (None if not validated yet)."""
    return plan.validation.status if plan.validation else None


def order_plans(plans: list[RecoveryPlan]) -> list[RecoveryPlan]:
    """Ranked plans first (by rank), then the rest: needs confirmation before infeasible."""
    def sort_key(plan: RecoveryPlan) -> tuple:
        """Rank first; unranked plans after, by status, then by ID."""
        status = status_of(plan)
        return (plan.rank is None, plan.rank or 0, STATUS_ORDER.get(status, 3), plan.id)
    return sorted(plans, key=sort_key)


# --- The parts of the explanation -------------------------------------------------------------


def summary(incident: NormalizedIncident, impact: ImpactResult, plans: list[RecoveryPlan],
            snapshot: BusinessSnapshot | None) -> str:
    """Two or three sentences: what happened, what it affects, and how many plans are usable."""
    who = label(incident.supplier_id, snapshot) if incident.supplier_id else "A supplier"
    qty = f"{incident.quantity_affected} " if incident.quantity_affected else "some "
    items = qty + _items_name(incident, snapshot)
    if incident.type == DisruptionType.SUPPLIER_SHORTFALL:
        text = f"{who} cannot supply {items} (originally due {fmt_date(incident.original_arrival_date)})."
    else:
        text = (f"{who} will deliver {items} late: originally due {fmt_date(incident.original_arrival_date)}, "
                f"now expected {fmt_date(incident.new_arrival_date)}.")

    affected = impact.affected_entities
    if affected:
        text += f" This affects {len(affected)} record(s): {', '.join(e.entity_id for e in affected)}."
    else:
        text += " No affected records were found."
    if impact.checked_not_affected:
        text += f" Checked and not affected: {', '.join(c.entity_id for c in impact.checked_not_affected)}."

    feasible = [p.id for p in plans if status_of(p) == ValidationStatus.FEASIBLE]
    text += f" {len(plans)} recovery plan(s) were checked; feasible: {', '.join(feasible) if feasible else 'none'}."
    return text


def plan_items(plan: RecoveryPlan) -> RawPlanComparison:
    """One plan's benefits and limitations, keyed by source, from its checks, assumptions and cost."""
    benefits: list[RawItem] = []
    limitations: list[RawItem] = []
    if plan.validation is None:
        limitations.append(RawItem(source="validation", text="This plan has not been validated yet."))
    else:
        for check in plan.validation.checks:
            if check.result == CheckResult.PASS:
                benefits.append(RawItem(source=check.code.value, text=check.detail))
            elif check.result == CheckResult.FAIL:
                limitations.append(RawItem(source=check.code.value, text=f"Fails: {check.detail}"))
            else:
                limitations.append(RawItem(source=check.code.value, text=f"Not confirmed yet: {check.detail}"))
    for number, assumption in enumerate(plan.assumptions, start=1):
        limitations.append(RawItem(source=f"assumption:{number}", text=f"Assumes: {assumption}"))
    if plan.estimated_cost is not None:
        benefits.append(RawItem(source="cost", text=f"Estimated cost: {fmt_money(plan.estimated_cost)}."))
    return RawPlanComparison(plan_id=plan.id, benefits=benefits, limitations=limitations)


def missing_confirmations(incident: NormalizedIncident, impact: ImpactResult, plans: list[RecoveryPlan]) -> list[str]:
    """Everything the owner still has to confirm: open incident fields, unknown facts, plan assumptions."""
    items = [f"Incident: {u.field} ({u.reason.value}){': ' + u.note if u.note else ''}"
             for u in incident.unresolved_fields]
    items += [f"Impact: {fact.get('note') or fact.get('fact') or fact}" for fact in impact.unresolved_facts]
    for plan in plans:
        if plan.validation is not None:
            items += [f"{plan.id}: confirm that {a}" for a in plan.validation.unresolved_assumptions]
    return list(dict.fromkeys(items))


def next_steps(impact: ImpactResult, plans: list[RecoveryPlan]) -> list[str]:
    """What the owner can do next. Only a feasible plan is ever offered for approval."""
    by_status: dict[ValidationStatus | None, list[str]] = {}
    for plan in plans:
        by_status.setdefault(status_of(plan), []).append(plan.id)

    steps = []
    feasible = by_status.get(ValidationStatus.FEASIBLE, [])
    if feasible:
        steps.append(f"Review {feasible[0]} and approve or reject it.")
        if len(feasible) > 1:
            steps.append(f"Other feasible plans to compare: {', '.join(feasible[1:])}.")
    else:
        steps.append("No plan is feasible yet: confirm the missing facts or edit a plan, then validate it again.")
    for plan_id in by_status.get(ValidationStatus.NEEDS_CONFIRMATION, []):
        steps.append(f"{plan_id} needs confirmation first; it must be validated again before it can be approved.")
    infeasible = by_status.get(ValidationStatus.INFEASIBLE, [])
    if infeasible:
        steps.append(f"Do not use {', '.join(infeasible)} as it stands: it failed validation.")
    if by_status.get(None):
        steps.append(f"Validate {', '.join(by_status[None])} before deciding.")
    if impact.unresolved_facts:
        steps.append("Confirm the unknown facts listed under missing confirmations.")
    return steps
