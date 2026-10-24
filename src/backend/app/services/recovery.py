import re
from typing import Any

from pydantic import ValidationError

import scdc.recovery as p4
import scdc.recovery.contracts as p4c
from app.errors import ApiError, ErrorCode
from contracts import NormalizedIncident, ImpactResult, BusinessSnapshot, RecoveryPlan

# Person 4's planner has its own copy of the contract models; the two sets are identical, so a JSON round-trip converts.
def to_p4(model: Any, p4_class: type) -> Any:
    return p4_class.model_validate(model.model_dump(mode="json"))

def from_p4(plan: p4c.RecoveryPlan) -> RecoveryPlan:
    return RecoveryPlan.model_validate(plan.model_dump(mode="json"))

def to_p4_inputs(incident: NormalizedIncident, snapshot: BusinessSnapshot, impact: ImpactResult):
    return (to_p4(incident, p4c.NormalizedIncident), to_p4(snapshot, p4c.BusinessSnapshot), to_p4(impact, p4c.ImpactResult))

# Argument order follows CONTRACTS §5 (incident, snapshot, impact), so don't reorder it.
# The planner is given the next free plan and action numbers, so its IDs never clash with earlier disruptions
# and the IDs inside each plan (its validation, its checks) already agree with the plan's own ID.
# Returns the plans in ranked order, the planner's warnings, and what the owner should do next.
def generate_plans(incident: NormalizedIncident, snapshot: BusinessSnapshot, impact: ImpactResult,
                   next_plan: int = 1, next_action: int = 1) -> tuple[list[RecoveryPlan], list[str], list[str]]:
    try:
        result = p4.plan_recovery(*to_p4_inputs(incident, snapshot, impact),
                                  ids=p4.IdFactory(next_plan=next_plan, next_action=next_action))
    except p4.RecoveryInputError as error:
        raise ApiError(status_code=409, code=ErrorCode.INVALID_STATE_TRANSITION,
                       detail=f"Plans can't be made yet: {error}") from error
    return [from_p4(plan) for plan in result.plans], result.warnings, result.next_steps()

# Person 4's edit_plan keeps the old title and adds " (edited, vN)" each time. The version belongs in the badge, so the
# title is rebuilt here: the suffixes go, and each changed quantity is swapped in ("Rent 20 chairs" -> "Rent 10 chairs").
def retitle(summary: str, old_actions: list[Any], new_actions: list[Any]) -> str:
    text = re.sub(r"(?: \(edited, v\d+\))+$", "", summary)
    before = {a.id: a.parameters.get("quantity") for a in old_actions}
    for action in new_actions:
        was, now = before.get(action.id), action.parameters.get("quantity")
        if isinstance(was, int) and isinstance(now, int) and was != now:
            # "20 chairs" -> "10 chairs"; a single item takes the singular ("1 chair").
            text = re.sub(rf"(?<![\d.]){was}(?![\d.])( \w+?)?(s?)\b",
                          lambda m: f"{now}{(m[1] or '') + (m[2] if now != 1 else '')}", text, count=1)
    return text

# An edit is always a new, revalidated version; the old one comes back as "superseded".
def edit_plan(plan: RecoveryPlan, base_version: int, actions: list[dict[str, Any]], assumptions: list[str] | None,
              incident: NormalizedIncident, snapshot: BusinessSnapshot, impact: ImpactResult) -> tuple[RecoveryPlan, RecoveryPlan]:
    p4_incident, p4_snapshot, p4_impact = to_p4_inputs(incident, snapshot, impact)
    try:
        old, new = p4.edit_plan(to_p4(plan, p4c.RecoveryPlan), base_version=base_version, actions=actions,
                                assumptions=assumptions, snapshot=p4_snapshot, impact=p4_impact, incident=p4_incident)
    except p4.StalePlanVersion as error:
        raise ApiError(status_code=409, code=ErrorCode.STALE_PLAN_VERSION, detail=str(error)) from error
    except ValidationError as error:
        raise ApiError(status_code=422, code=ErrorCode.VALIDATION_ERROR,
                       detail="One of the actions is not valid; check its type, target and dates.") from error
    new = from_p4(new)
    new.summary = retitle(plan.summary, plan.actions, new.actions)
    return from_p4(old), new

def revalidate_plan(plan: RecoveryPlan, incident: NormalizedIncident, snapshot: BusinessSnapshot, impact: ImpactResult) -> RecoveryPlan:
    p4_incident, p4_snapshot, p4_impact = to_p4_inputs(incident, snapshot, impact)
    return from_p4(p4.revalidate(to_p4(plan, p4c.RecoveryPlan), p4_snapshot, p4_impact, p4_incident))

# The ranking of a disruption's plans, recomputed after one of them changed.
def rank_plans(plans: list[RecoveryPlan], incident: NormalizedIncident, snapshot: BusinessSnapshot,
               impact: ImpactResult) -> list[RecoveryPlan]:
    _, _, p4_impact = to_p4_inputs(incident, snapshot, impact)
    jobs = {c.id: c.job_id for c in snapshot.commitments}
    requirements = {(d.target_id, d.source_id): d.required_quantity for d in snapshot.dependencies
                    if d.dependency_type.value == "requires" and d.required_quantity is not None}
    ranked = p4.rank_plans([to_p4(plan, p4c.RecoveryPlan) for plan in plans], p4_impact, jobs, requirements=requirements)
    return [from_p4(plan) for plan in ranked]
