"""Module B: explain the impact and the recovery plans in plain language.

    explain(incident, impact, plans, *, snapshot=None, adapter=None) -> Explanation

Steps (agreed in v2 step 3d):
1. Build the template explanation (always; it is the fallback).
2. Ask the model to write from the FACTS. Any model failure (unavailable, timeout, invalid reply)
   means the template is returned, with no retry.
3. Merge item by item, in the template's order:
     model item passes the claim check      -> the model's text
     model item fails the claim check       -> the template's item   (counted as removed)
     model item with an unknown key/record  -> dropped               (counted as removed)
     model left the item out                -> the template's item   (not counted)
4. If no model text survives, the result is reported as the template (generated_by "template").
Missing confirmations and next steps always come from code; plan statuses are copied from P4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .adapter import ModelAdapter, ModelError, ModelOutputError, NoModelAdapter, call_model
from .claims import ID_RE, CheckContext, FactSheet, facts_for_impact, facts_for_plan, facts_for_summary, find_problems
from .explanation_template import ExplanationTemplate, assemble, build_template, fmt_money, label, order_plans, status_of
from .prompts import WEEKDAYS, build_explanation_request
from .schemas import (
    BusinessSnapshot,
    Explanation,
    ImpactExplanation,
    ImpactResult,
    NormalizedIncident,
    RawExplanation,
    RawItem,
    RawPlanComparison,
    RecoveryPlan,
)


@dataclass
class MergeOutcome:
    """The checked texts, how many model items were removed, and how many were used."""

    texts: RawExplanation
    removed: int
    used: int


def explain(
    incident: NormalizedIncident,
    impact: ImpactResult,
    plans: list[RecoveryPlan],
    *,
    snapshot: BusinessSnapshot | None = None,
    adapter: ModelAdapter | None = None,
) -> Explanation:
    """Explain the disruption: the model's checked text where it holds up, the template everywhere else.

    `adapter=None` means no model: the template explanation is returned. Never raises on model failure.
    """
    ordered = order_plans(plans)
    template = build_template(incident, impact, ordered, snapshot=snapshot)
    try:
        raw, model_name = write_with_model(explanation_facts(incident, impact, ordered, template, snapshot),
                                           impact.disruption_id, adapter or NoModelAdapter())
    except ModelError:
        return assemble(template.raw, template, impact, ordered, generated_by="template", fallback_used=True)

    outcome = merge_checked(raw, template, incident, impact, ordered, snapshot)
    if outcome.used == 0:
        return assemble(template.raw, template, impact, ordered, generated_by="template", fallback_used=True,
                        unsupported_claims_removed=outcome.removed)
    return assemble(outcome.texts, template, impact, ordered, generated_by=f"model:{model_name}",
                    fallback_used=False, unsupported_claims_removed=outcome.removed)


def write_with_model(facts: dict, fixture_key: str, adapter: ModelAdapter) -> tuple[RawExplanation, str]:
    """Ask the model to write the explanation; return its validated reply and the model's name."""
    response = call_model(adapter, build_explanation_request(facts, fixture_key))
    try:
        return RawExplanation.model_validate_json(response.text), response.model
    except ValidationError as error:
        raise ModelOutputError(f"Invalid explanation reply: {error.error_count()} problem(s)") from error


# --- What the model is given ----------------------------------------------------------------


def _names(ids: set[str], snapshot: BusinessSnapshot | None) -> dict[str, str]:
    """Readable names for the record IDs in the facts, e.g. {"S-02": "Cahaya Event Rentals (S-02)"}."""
    if snapshot is None:
        return {}
    return {i: label(i, snapshot) for i in sorted(ids) if label(i, snapshot) != i}


def explanation_facts(incident: NormalizedIncident, impact: ImpactResult, plans: list[RecoveryPlan],
                      template: ExplanationTemplate, snapshot: BusinessSnapshot | None) -> dict[str, Any]:
    """The FACTS sent to the model: the data, record names, and which benefit/limitation keys to write."""
    keys = {c.plan_id: c for c in template.raw.plan_comparisons}
    reported_on = incident.reported_at.date()
    facts: dict[str, Any] = {
        "report_date": reported_on.isoformat(),
        "report_weekday": WEEKDAYS[reported_on.weekday()],
        "incident": incident.model_dump(mode="json", include={
            "type", "supplier_id", "resource_id", "delivery_id", "quantity_affected",
            "original_arrival_date", "new_arrival_date", "description"}),
        "affected_entities": [e.model_dump(mode="json", exclude={"severity"}) for e in impact.affected_entities],
        "checked_not_affected": [c.model_dump(mode="json") for c in impact.checked_not_affected],
        "resource_shortfalls": [s.model_dump(mode="json") for s in impact.resource_shortfalls],
        "plans": [
            {
                "plan_id": p.id,
                "validation_status": status_of(p).value if status_of(p) else "not_validated",
                "summary": p.summary,
                "actions": [{"action_type": a.action_type.value, "parameters": a.parameters} for a in p.actions],
                "checks": [c.model_dump(mode="json", include={"code", "result", "detail"})
                           for c in (p.validation.checks if p.validation else [])],
                "assumptions": p.assumptions,
                "estimated_cost": fmt_money(p.estimated_cost) if p.estimated_cost else None,
                "benefit_keys": [b.source for b in keys[p.id].benefits],
                "limitation_keys": [x.source for x in keys[p.id].limitations],
            }
            for p in plans
        ],
    }
    facts["names"] = _names(set(ID_RE.findall(str(facts))), snapshot)
    return facts


# --- Merging the model's text with the template ---------------------------------------------------


class _Merger:
    """Walks the template item by item and keeps each model item only if it passes the claim check."""

    def __init__(self, incident: NormalizedIncident, plans: list[RecoveryPlan]) -> None:
        """Set up the context shared by every check, and the counters."""
        self.base = CheckContext(incident.reported_at.date(), incident.original_arrival_date,
                                 {p.id: status_of(p) for p in plans})
        self.removed = 0
        self.used = 0

    def pick(self, model_text: str | None, template_text: str, facts: FactSheet, context: CheckContext) -> str:
        """The model's text if it is backed by the facts, else the template's (counting the replacement)."""
        if model_text is None:
            return template_text
        if find_problems(model_text, facts, context):
            self.removed += 1
            return template_text
        self.used += 1
        return model_text

    def keyed(self, items: list[Any], key: str, allowed: set[str]) -> dict[str, Any]:
        """Model items by key (first one wins); items whose key the template does not have are counted as removed."""
        found: dict[str, Any] = {}
        for item in items:
            value = getattr(item, key)
            if value not in allowed:
                self.removed += 1
            else:
                found.setdefault(value, item)
        return found

    def context(self, *, plan_id: str | None = None, affected: bool = False) -> CheckContext:
        """The shared context, narrowed to one plan or to an affected record."""
        return CheckContext(self.base.reported_on, self.base.anchor, self.base.plan_statuses, plan_id, affected)


def merge_checked(raw: RawExplanation, template: ExplanationTemplate, incident: NormalizedIncident,
                  impact: ImpactResult, plans: list[RecoveryPlan], snapshot: BusinessSnapshot | None) -> MergeOutcome:
    """Combine the model's reply with the template, item by item (see the module docstring)."""
    merger = _Merger(incident, plans)
    summary = merger.pick(raw.summary, template.raw.summary,
                          facts_for_summary(incident, impact, plans, snapshot), merger.context())

    entities = {e.entity_id: e for e in impact.affected_entities}
    model_impacts = merger.keyed(raw.impact_explanations, "entity_id", {t.entity_id for t in template.raw.impact_explanations})
    impacts = [
        ImpactExplanation(entity_id=t.entity_id, text=merger.pick(
            getattr(model_impacts.get(t.entity_id), "text", None), t.text,
            facts_for_impact(entities[t.entity_id], incident, impact, snapshot), merger.context(affected=True)))
        for t in template.raw.impact_explanations
    ]

    by_id = {p.id: p for p in plans}
    model_plans = merger.keyed(raw.plan_comparisons, "plan_id", {t.plan_id for t in template.raw.plan_comparisons})
    comparisons = []
    for t in template.raw.plan_comparisons:
        model = model_plans.get(t.plan_id, RawPlanComparison(plan_id=t.plan_id))
        facts = facts_for_plan(by_id[t.plan_id], incident, impact, snapshot)
        context = merger.context(plan_id=t.plan_id)

        def merged(template_items: list[RawItem], model_items: list[RawItem]) -> list[RawItem]:
            """One list (benefits or limitations): the model's item per key where it passes, else the template's."""
            found = merger.keyed(model_items, "source", {i.source for i in template_items})
            return [RawItem(source=i.source, text=merger.pick(getattr(found.get(i.source), "text", None), i.text,
                                                               facts, context))
                    for i in template_items]

        comparisons.append(RawPlanComparison(plan_id=t.plan_id, benefits=merged(t.benefits, model.benefits),
                                             limitations=merged(t.limitations, model.limitations)))

    texts = RawExplanation(summary=summary, impact_explanations=impacts, plan_comparisons=comparisons)
    return MergeOutcome(texts, merger.removed, merger.used)
