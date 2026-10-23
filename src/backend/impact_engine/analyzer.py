"""The impact-analysis algorithm  (CONTRACTS section 5:  analyze_impact(incident, snapshot) -> ImpactResult).

Pipeline (numbers match SCDC_P3.md "Algorithm Requirements"):

 1. Build a directed dependency graph          graph.build_graph
 2. Identify the directly affected entity      the delayed delivery (and its supplier / resource)
 3. Traverse dependency edges downstream       DependencyGraph.all_paths
 4. Deduplicate entities, keep every path      one entry per entity, all routes in dependency_paths
 5. Check quantities / recorded availability   inventory rule of CONTRACTS section 4
 6. Check dates and deadlines                  the delay window vs. each job's required_by date
 7. Classify confirmed / potential / unresolved
 8. Score severity (transparent, configurable)
 9. Explain every finding with evidence
10. Return the structured ImpactResult

Inventory rule (CONTRACTS section 4): a reusable resource is occupied only on the day a job
needs it and comes back the next day, so jobs needing the resource on DIFFERENT days do not
compete. Available on day d = on_hand + inbound deliveries expected strictly BEFORE d.
The incident moves `quantity_affected` units of one delivery from its original date to
`new_arrival_date`; the disruption's effect is the difference between supply with and without it.

Everything here is deterministic. No AI decides what depends on what.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Mapping, Optional, Union

from pydantic import ValidationError

from .config import SeverityConfig
from .graph import build_graph
from .loader import snapshot_from_raw, summarise
from .models import (
    AffectedEntity,
    AnalysisStatus,
    BusinessSnapshot,
    CheckedNotAffected,
    DataIssue,
    DependencyType,
    DisruptionType,
    EntityType,
    Evidence,
    ImpactResult,
    ImpactStatus,
    IssueCode,
    IssueSeverity,
    Job,
    NormalizedIncident,
    Priority,
    ResourceShortfall,
    SeverityBreakdown,
    UnresolvedFact,
    UnresolvedReason,
)
from .validation import build_context

ACTIVE_DELIVERY = {"scheduled", "delayed"}
INACTIVE_JOB = {"cancelled", "canceled", "completed", "closed"}


class _V(Enum):
    """Internal verdict. Lower value = more serious."""
    CONFIRMED = 0
    POTENTIAL = 1
    UNRESOLVED = 2
    CLEARED = 3


_STATUS = {_V.CONFIRMED: ImpactStatus.CONFIRMED, _V.POTENTIAL: ImpactStatus.POTENTIAL_RISK,
           _V.UNRESOLVED: ImpactStatus.UNRESOLVED}
_STATUS_RANK = {ImpactStatus.CONFIRMED: 0, ImpactStatus.POTENTIAL_RISK: 1, ImpactStatus.UNRESOLVED: 2}
_TYPE_RANK = {EntityType.RESOURCE: 0, EntityType.JOB: 1, EntityType.COMMITMENT: 2}


@dataclass
class _Finding:
    verdict: _V
    needed_by: date
    reason: str
    evidence: list[Evidence] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    ratio: Optional[float] = None       # pool shortfall / pool demand, None = not measurable
    breakdown: Optional[SeverityBreakdown] = None
    job: Optional[Job] = None


@dataclass
class _Member:
    job: Job
    dep_id: Optional[str]
    day: date
    demand: Optional[int]
    conflict: Optional[str]


class _FactBook:
    """Collects unresolved facts, merging the entities each one blocks."""

    def __init__(self) -> None:
        self._facts: dict[tuple[str, str], UnresolvedFact] = {}

    def add(self, entity_id: str, field_name: str, reason: UnresolvedReason, note: str,
            affects: Union[tuple[str, ...], list[str]] = ()) -> str:
        key = (entity_id, field_name)
        fact = self._facts.get(key)
        if fact is None:
            fact = UnresolvedFact(entity_id=entity_id, field=field_name, reason=reason, note=note)
            self._facts[key] = fact
        for a in affects:
            if a not in fact.affects:
                fact.affects.append(a)
        return f"{entity_id}.{field_name}: {fact.note}"

    def all(self) -> list[UnresolvedFact]:
        out = sorted(self._facts.values(), key=lambda f: (f.entity_id, f.field))
        for f in out:
            f.affects.sort()
        return out


# --------------------------------------------------------------------------- #
# Severity (stage 8)
# --------------------------------------------------------------------------- #
def _band(score: float, config: SeverityConfig) -> Priority:
    if score >= config.threshold_critical:
        return Priority.CRITICAL
    if score >= config.threshold_high:
        return Priority.HIGH
    if score >= config.threshold_medium:
        return Priority.MEDIUM
    return Priority.LOW


def _score(config: SeverityConfig, priority: Priority, needed_by: date, as_of: date,
           ratio: Optional[float]) -> SeverityBreakdown:
    """severity = 10 * (w1*urgency + w2*shortfall + w3*importance) / (w1+w2+w3)

    urgency    = 1 - clamp(days_until_needed / horizon, 0, 1)
    shortfall  = units short for the whole pool / units the pool needs that day  (0..1)
    importance = config.priority_importance[job.priority]
    """
    urgency = 1.0 - min(max((needed_by - as_of).days / config.urgency_horizon_days, 0.0), 1.0)
    assumed: list[str] = []
    if ratio is None:
        shortfall = config.unknown_factor_default
        assumed.append("resource_shortfall")
    else:
        shortfall = min(max(ratio, 0.0), 1.0)
    importance = config.priority_importance.get(priority.value)
    if importance is None:
        importance = config.unknown_factor_default
        assumed.append("commitment_importance")
    w = {"deadline_urgency": config.weight_deadline_urgency,
         "resource_shortfall": config.weight_resource_shortfall,
         "commitment_importance": config.weight_commitment_importance}
    raw = (w["deadline_urgency"] * urgency + w["resource_shortfall"] * shortfall
           + w["commitment_importance"] * importance) / sum(w.values())
    return SeverityBreakdown(deadline_urgency=round(urgency, 3), resource_shortfall=round(shortfall, 3),
                             commitment_importance=round(importance, 3), weights=w,
                             score=round(10 * raw, 1), assumed_factors=assumed)


def _severity_int(score: float) -> int:
    return max(0, min(10, int(score + 0.5)))


def _plural(unit: str, n: Optional[int]) -> str:
    return unit if n == 1 else f"{unit}s"


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def analyze_impact(
    incident: Union[NormalizedIncident, Mapping[str, Any]],
    snapshot: Union[BusinessSnapshot, Mapping[str, Any]],
    config: Optional[SeverityConfig] = None,
    as_of: Optional[date] = None,
) -> ImpactResult:
    """Analyse one incident against one business snapshot.

    Never raises for bad business data: problems come back in `data_issues`,
    `unresolved_facts` and `analysis_status`. `as_of` defaults to the snapshot's date.
    """
    config = config or SeverityConfig()
    inc, bad = _parse_incident(incident)
    if inc is None:
        return _failed(_incident_id(incident), as_of, config, [bad], [])  # type: ignore[list-item]
    if isinstance(snapshot, BusinessSnapshot):
        snap = snapshot
    elif isinstance(snapshot, Mapping):
        snap = snapshot_from_raw(snapshot)
    else:
        return _failed(inc.id, as_of, config, [DataIssue(
            code=IssueCode.INVALID_RECORD, severity=IssueSeverity.ERROR,
            message="snapshot must be a BusinessSnapshot or a mapping.")], [])

    ctx = build_context(snap)
    issues = ctx.issues
    facts = _FactBook()
    if as_of is None:
        if snap.as_of is not None:
            as_of = snap.as_of.date()
        else:
            as_of = date.today()
            issues.append(DataIssue(code=IssueCode.STALE_OR_MISSING, severity=IssueSeverity.INFO,
                                    message="Snapshot has no as_of; today's date was used."))

    def fail(code: IssueCode, message: str, entity_id: Optional[str] = None) -> ImpactResult:
        issues.append(DataIssue(code=code, severity=IssueSeverity.ERROR, message=message, entity_id=entity_id))
        return _failed(inc.id, as_of, config, issues, facts.all())

    for item in snap.missing_or_stale:
        if isinstance(item, Mapping) and item.get("entity_id") and item.get("field"):
            facts.add(str(item["entity_id"]), str(item["field"]), _reason(item.get("reason")),
                      str(item.get("note") or "Reported missing or stale by the snapshot."))
        issues.append(DataIssue(code=IssueCode.STALE_OR_MISSING, severity=IssueSeverity.WARNING,
                                message=f"Snapshot reports missing or stale data: {item}"))

    if inc.type is not DisruptionType.SUPPLIER_DELAY:
        return fail(IssueCode.UNSUPPORTED_INCIDENT_TYPE,
                    f"Incident type '{inc.type.value}' is not supported yet; only supplier_delay is.")

    # ---- incident fields the extractor could not verify are treated as UNKNOWN ---- #
    unverified: dict[str, tuple[UnresolvedReason, str]] = {}
    for item in inc.unresolved_fields:
        if isinstance(item, str):
            name, reason, note = item, UnresolvedReason.UNVERIFIED, ""
        elif isinstance(item, Mapping) and item.get("field"):
            name, reason, note = str(item["field"]), _reason(item.get("reason")), str(item.get("note") or "")
        else:
            continue
        note = note or f"Incident field '{name}' could not be verified."
        unverified[name] = (reason, note)
        facts.add(inc.id, name, reason, note)

    def stated(name: str) -> Any:
        return None if name in unverified else getattr(inc, name)

    supplier_id, resource_id, delivery_id = stated("supplier_id"), stated("resource_id"), stated("delivery_id")

    # ---- Stage 2: which delivery is delayed? ------------------------------------- #
    if delivery_id is not None:
        delivery = ctx.deliveries.get(delivery_id)
        if delivery is None:
            return fail(IssueCode.UNKNOWN_ENTITY,
                        f"Delivery '{delivery_id}' named by the incident is not in the records.", delivery_id)
    else:
        candidates = sorted((d for d in ctx.deliveries.values()
                             if d.status in ACTIVE_DELIVERY
                             and (resource_id is not None or supplier_id is not None)
                             and (resource_id is None or d.resource_id == resource_id)
                             and (supplier_id is None or d.supplier_id == supplier_id)), key=lambda d: d.id)
        if len(candidates) != 1:
            facts.add(inc.id, "delivery_id",
                      UnresolvedReason.AMBIGUOUS if candidates else UnresolvedReason.MISSING,
                      "The incident does not identify which delivery is delayed.")
            return fail(IssueCode.INVALID_INCIDENT, "Cannot tell which delivery is delayed; clarification needed.")
        delivery = candidates[0]
        issues.append(DataIssue(code=IssueCode.DERIVED_EDGE, severity=IssueSeverity.INFO,
                                message=f"Incident has no delivery_id; the only matching delivery {delivery.id} was used.",
                                entity_id=delivery.id))
    if resource_id is not None and resource_id != delivery.resource_id:
        return fail(IssueCode.CONFLICTING_DATA,
                    f"Incident says resource {resource_id} but delivery {delivery.id} supplies {delivery.resource_id}.", delivery.id)
    if supplier_id is not None and supplier_id != delivery.supplier_id:
        return fail(IssueCode.CONFLICTING_DATA,
                    f"Incident says supplier {supplier_id} but delivery {delivery.id} comes from {delivery.supplier_id}.", delivery.id)
    if delivery.status not in ACTIVE_DELIVERY:
        return fail(IssueCode.CONFLICTING_DATA,
                    f"Delivery {delivery.id} has status '{delivery.status}' and cannot be delayed.", delivery.id)

    resource = ctx.resources[delivery.resource_id]
    rname, unit = resource.name or resource.id, resource.unit
    quantity = None if "quantity_affected" in unverified else inc.quantity_affected
    arrival = None if "new_arrival_date" in unverified else inc.new_arrival_date
    orig = delivery.expected_date  # the record, not the message, is authoritative
    if quantity is None:
        facts.add(inc.id, "quantity_affected", UnresolvedReason.MISSING, "The quantity affected by the delay is unknown.")
    if arrival is None:
        facts.add(inc.id, "new_arrival_date", UnresolvedReason.MISSING, "The new arrival date is unknown.")
    if inc.original_arrival_date is not None and inc.original_arrival_date != orig:
        issues.append(DataIssue(code=IssueCode.CONFLICTING_DATA, severity=IssueSeverity.WARNING,
                                message=f"Incident says the original arrival was {inc.original_arrival_date} but delivery "
                                        f"{delivery.id} is recorded for {orig}; the record was used.", entity_id=delivery.id))
    if arrival is not None and arrival <= orig:
        issues.append(DataIssue(code=IssueCode.CONFLICTING_DATA, severity=IssueSeverity.WARNING,
                                message=f"New arrival {arrival} is not later than the original {orig}; nothing is delayed.",
                                entity_id=delivery.id))

    # ---- Stages 1, 3, 4: graph, traversal, deduplication with all paths ---------- #
    graph = build_graph(ctx)
    paths, truncated, cycles = graph.all_paths(
        delivery.supplier_id,
        edge_filter=lambda e: not ((e.dependency_type is DependencyType.SHIPS and e.target != delivery.id)
                                   or (e.dependency_type is DependencyType.SUPPLIES and e.target != resource.id)),
        max_paths_per_node=config.max_paths_per_entity)
    for a, b in cycles:
        issues.append(DataIssue(code=IssueCode.CYCLE_DETECTED, severity=IssueSeverity.WARNING,
                                message=f"Circular dependency {a} -> {b}; the repeat was ignored."))
    for n in sorted(truncated):
        issues.append(DataIssue(code=IssueCode.PATHS_TRUNCATED, severity=IssueSeverity.WARNING,
                                message=f"More than {config.max_paths_per_entity} paths reach {n}; only the first were kept.",
                                entity_id=n))

    # ---- Stage 5a: can supply be computed at all? --------------------------------- #
    blockers: list[tuple[str, str, UnresolvedReason, str]] = []  # (entity, field, reason, note)
    if resource.on_hand_quantity is None:
        blockers.append((resource.id, "on_hand_quantity", UnresolvedReason.MISSING,
                         f"On-hand quantity of {rname} is not recorded."))
    if quantity is None:
        blockers.append((inc.id, "quantity_affected", unverified.get("quantity_affected", (UnresolvedReason.MISSING,))[0],
                         "The quantity affected by the delay is unknown."))
    elif quantity > delivery.quantity:
        blockers.append((delivery.id, "quantity", UnresolvedReason.CONFLICTING,
                         f"The incident delays {quantity} but delivery {delivery.id} is only {delivery.quantity}."))
        issues.append(DataIssue(code=IssueCode.CONFLICTING_DATA, severity=IssueSeverity.WARNING,
                                message=f"Incident delays {quantity} {_plural(unit, quantity)} but delivery {delivery.id} "
                                        f"is only {delivery.quantity}.", entity_id=delivery.id))
    if not resource.reusable:
        blockers.append((resource.id, "reusable", UnresolvedReason.UNVERIFIED,
                         f"{rname} is not reusable; stock depletion across jobs is not modelled."))
    for d in sorted(ctx.deliveries.values(), key=lambda x: x.id):
        if d.resource_id == resource.id and d.status == "partially_delivered":
            blockers.append((d.id, "quantity", UnresolvedReason.MISSING,
                             f"Delivery {d.id} is partially delivered and the remaining quantity is not recorded."))

    # Inbound units with and without the incident (stage 6: dates).
    before: list[tuple[date, int]] = []
    after: list[tuple[date, int]] = []
    moved = min(quantity or 0, delivery.quantity)
    for d in sorted(ctx.deliveries.values(), key=lambda x: x.id):
        if d.resource_id != resource.id or d.status not in ACTIVE_DELIVERY:
            continue
        before.append((d.expected_date, d.quantity))
        if d.id == delivery.id:
            after.append((d.expected_date, d.quantity - moved))
            if arrival is not None and moved:
                after.append((arrival, moved))
        else:
            after.append((d.expected_date, d.quantity))
    on_hand = resource.on_hand_quantity or 0

    def supply(units: list[tuple[date, int]], day: date) -> int:
        return on_hand + sum(q for dt, q in units if dt < day)  # strictly before the day

    def in_window(day: date) -> bool:
        """True when the delay changes what is available on `day`."""
        return quantity != 0 and day > orig and (arrival is None or day <= arrival)

    qtxt = f"{quantity} {_plural(unit, quantity)}" if quantity is not None else "the delayed units"
    delay_text = (f"{quantity} of {delivery.quantity} delayed from {orig} to "
                  f"{arrival if arrival is not None else 'an unknown date'}")

    # ---- Stage 5b: demand, grouped by the day it is needed ------------------------ #
    findings: dict[str, _Finding] = {}
    by_day: dict[date, list[_Member]] = defaultdict(list)
    for e in sorted((x for x in graph.out_edges(resource.id) if x.dependency_type is DependencyType.REQUIRES),
                    key=lambda x: x.target):
        job = ctx.jobs[e.target]
        day = e.required_by or job.event_date
        jname = job.name or job.id
        if job.status.lower() in INACTIVE_JOB:
            findings[job.id] = _Finding(_V.CLEARED, day, f"{jname} is {job.status}; the delay has no operational effect.",
                                        [Evidence(entity_id=job.id, fact=f"status={job.status}")], job=job)
            continue
        conflict = ctx.conflicted_requirements.get((resource.id, job.id))
        by_day[day].append(_Member(job, e.dependency_id, day, None if conflict else e.required_quantity, conflict))

    def dep_evidence(m: _Member) -> list[Evidence]:
        fact = f"required_quantity={m.demand if m.demand is not None else 'unknown'}, required_by={m.day}"
        return [Evidence(entity_id=m.dep_id or m.job.id, fact=fact)]

    def demand_fact(m: _Member) -> str:
        if m.conflict:
            return facts.add(f"{resource.id}->{m.job.id}", "required_quantity", UnresolvedReason.CONFLICTING,
                             f"Conflicting required quantities are recorded ({m.conflict}).", [m.job.id])
        return facts.add(f"{resource.id}->{m.job.id}", "required_quantity", UnresolvedReason.MISSING,
                         "The required quantity is not recorded.", [m.job.id])

    shortfalls: list[ResourceShortfall] = []
    exposed_jobs: list[str] = []
    resource_sentences: list[str] = []

    # ---- Stages 5c-7: evaluate each day's shared pool ----------------------------- #
    for day in sorted(by_day):
        members = by_day[day]
        known = [m for m in members if m.demand is not None]
        unknown = [m for m in members if m.demand is None]
        total = sum(m.demand for m in known)  # type: ignore[misc]
        demand_list = ", ".join(f"{m.job.id}={m.demand}" for m in known)

        if not in_window(day):  # delay does not touch this day
            s_after = None if blockers else supply(after, day)
            for m in members:
                if quantity == 0:
                    why = "No units are delayed."
                elif arrival is not None and arrival <= orig:
                    why = "The new arrival date is not later than the original; nothing is delayed."
                elif day <= orig:
                    why = f"Needed {day}, on or before the original arrival {orig}; the delay does not change what is available."
                else:
                    why = f"Needed {day}; the delayed {qtxt} arrive {arrival}"
                    why += (f", so {s_after} are available against {total} required." if s_after is not None and not unknown else ".")
                findings[m.job.id] = _Finding(_V.CLEARED, day, why, dep_evidence(m), job=m.job)
            continue

        exposed_jobs.extend(m.job.id for m in members)

        if blockers:  # supply cannot be verified -> nothing can be confirmed or cleared
            notes = " ".join(b[3] for b in blockers)
            if notes not in resource_sentences:
                resource_sentences.append(notes)
            for m in members:
                missing = [facts.add(eid, fld, rsn, note, [m.job.id]) for eid, fld, rsn, note in blockers]
                if m.demand is None:
                    missing.append(demand_fact(m))
                findings[m.job.id] = _Finding(
                    _V.UNRESOLVED, day, f"Cannot verify the impact on {m.job.name or m.job.id}: {notes}",
                    dep_evidence(m) + [Evidence(entity_id=delivery.id, fact=delay_text)], missing, job=m.job)
            continue

        s_before, s_after = supply(before, day), supply(after, day)
        short_before, short_after = max(0, total - s_before), max(0, total - s_after)
        caveats: list[str] = []
        if arrival is None:
            caveats.append("the new arrival date is unknown, so the delayed units are assumed not to arrive")
        if not resource.on_hand_verified:
            caveats.append("the on-hand count has not been verified")
        supply_ev = Evidence(entity_id=resource.id,
                             fact=f"available on {day} = {s_after} (on_hand_quantity={on_hand} + {s_after - on_hand} "
                                  f"arriving before {day}); required = {total} ({demand_list})")
        delay_ev = Evidence(entity_id=delivery.id, fact=delay_text)

        for m in unknown:
            findings[m.job.id] = _Finding(
                _V.UNRESOLVED, day,
                f"Cannot determine the impact on {m.job.name or m.job.id}: the quantity of {rname} it needs is unknown or contradictory.",
                dep_evidence(m) + [delay_ev], [demand_fact(m)], job=m.job)

        # Inside the delay window supply drops by exactly the delayed units, so this is true whenever
        # the pool is short after the delay. Written as a comparison to state the intent: the SHORTFALL
        # is attributable to the delay (any pre-existing part is reported in the evidence).
        attributable = short_after > short_before
        if attributable and known:
            shortfalls.append(ResourceShortfall(resource_id=resource.id, date=day, required=total,
                                                available=s_after, shortfall=short_after))
            sentence = f"Only {s_after} {_plural(unit, s_after)} available on {day} against {total} required."
            resource_sentences.append(sentence + (f" Caveat: {'; '.join(caveats)}." if caveats else ""))

        for m in known:
            jname = m.job.name or m.job.id
            ev = dep_evidence(m) + [supply_ev, delay_ev]
            if m.demand == 0:
                findings[m.job.id] = _Finding(_V.CLEARED, day, f"{jname} requires 0 {_plural(unit, 0)}.", ev, job=m.job)
            elif attributable:
                missing = []
                if arrival is None:
                    missing.append(facts.add(inc.id, "new_arrival_date", UnresolvedReason.MISSING,
                                             "The new arrival date is unknown.", [m.job.id]))
                if not resource.on_hand_verified:
                    missing.append(facts.add(resource.id, "on_hand_quantity", UnresolvedReason.UNVERIFIED,
                                             "The on-hand count has not been verified.", [m.job.id]))
                if short_before > 0:
                    ev.append(Evidence(entity_id=resource.id,
                                       fact=f"without the delay the shortfall on {day} would still be {short_before}"))
                reason = (f"{'Shared ' if len(known) > 1 else ''}{rname} pool short by {short_after} on {day}; "
                          f"{m.job.id} requires {m.demand}.")
                if caveats:
                    reason += f" Not confirmed: {'; '.join(caveats)}."
                findings[m.job.id] = _Finding(_V.POTENTIAL if caveats else _V.CONFIRMED, day, reason, ev, missing,
                                              short_after / total, job=m.job)
            elif unknown:
                ids = ", ".join(sorted(u.job.id for u in unknown))
                findings[m.job.id] = _Finding(
                    _V.POTENTIAL, day,
                    f"Known demand ({total}) fits within the {s_after} available on {day}, but {ids} also "
                    f"{'requires' if len(unknown) == 1 else 'require'} {rname} that day with an unknown quantity.",
                    ev, [demand_fact(u) for u in unknown], None, job=m.job)
            else:
                findings[m.job.id] = _Finding(
                    _V.CLEARED, day,
                    f"{s_after} {_plural(unit, s_after)} available on {day} after the delay against {total} required "
                    f"(spare {s_after - total}).", ev, job=m.job)
        if unknown and not attributable and known:
            resource_sentences.append(f"May be short on {day}: some required quantities are unknown.")

    # ---- Stage 8: severity -------------------------------------------------------- #
    for f in findings.values():
        if f.verdict in (_V.CONFIRMED, _V.POTENTIAL) and f.job is not None:
            f.breakdown = _score(config, f.job.priority, f.needed_by, as_of, f.ratio)

    # ---- Stages 9-10: assemble ---------------------------------------------------- #
    affected: list[AffectedEntity] = []
    cleared: list[CheckedNotAffected] = []

    def entity(kind: EntityType, entity_id: str, verdict: _V, reason: str, evidence: list[Evidence],
               missing: list[str], breakdown: Optional[SeverityBreakdown]) -> AffectedEntity:
        epaths = paths.get(entity_id, [])
        return AffectedEntity(
            entity_type=kind, entity_id=entity_id, impact_status=_STATUS[verdict], reason=reason,
            severity=_severity_int(breakdown.score) if breakdown else None,
            priority=_band(breakdown.score, config) if breakdown else None,
            severity_breakdown=breakdown, dependency_path=epaths[0] if epaths else [],
            dependency_paths=epaths, evidence=evidence, missing_information=missing)

    for job_id in sorted(findings):
        f = findings[job_id]
        if f.verdict is _V.CLEARED:
            cleared.append(CheckedNotAffected(entity_type=EntityType.JOB, entity_id=job_id, reason=f.reason,
                                              dependency_paths=paths.get(job_id, [])))
        else:
            affected.append(entity(EntityType.JOB, job_id, f.verdict, f.reason, f.evidence, f.missing, f.breakdown))

    # commitments take the worst status of the job(s) that fulfil them
    for cm in sorted(ctx.commitments.values(), key=lambda c: c.id):
        preds = sorted({e.source for e in graph.in_edges(cm.id)
                        if e.dependency_type is DependencyType.FULFILS and e.source in findings})
        if cm.id not in paths or not preds:
            continue
        hit = [(p, findings[p]) for p in preds if findings[p].verdict is not _V.CLEARED]
        if not hit:
            cleared.append(CheckedNotAffected(entity_type=EntityType.COMMITMENT, entity_id=cm.id,
                                              reason=f"{', '.join(preds)} not affected.", dependency_paths=paths[cm.id]))
            continue
        verdict = min((f.verdict for _, f in hit), key=lambda v: v.value)
        best = max((f for _, f in hit if f.breakdown), key=lambda f: f.breakdown.score, default=None)  # type: ignore[union-attr]
        flag = {True: "reschedulable", False: "not reschedulable"}.get(cm.reschedulable)  # type: ignore[arg-type]
        evidence = [Evidence(entity_id=cm.id, fact=f"reschedulable={str(cm.reschedulable).lower()}")] if cm.reschedulable is not None else []
        missing = sorted({m for _, f in hit for m in f.missing})
        affected.append(entity(EntityType.COMMITMENT, cm.id, verdict,
                               f"Depends on {', '.join(p for p, _ in hit)}" + (f"; {flag}." if flag else "."),
                               evidence, missing, best.breakdown if best else None))

    # the resource itself: affected if any job competing for it in the delay window is affected
    res_hits = [findings[j] for j in exposed_jobs if findings[j].verdict is not _V.CLEARED]
    res_paths = paths.get(resource.id, [])
    if res_hits:
        verdict = min((f.verdict for f in res_hits), key=lambda v: v.value)
        best = max((f for f in res_hits if f.breakdown), key=lambda f: f.breakdown.score, default=None)  # type: ignore[union-attr]
        if verdict is _V.UNRESOLVED:
            reason = f"Cannot verify whether the {rname} supply is short: " + " ".join(resource_sentences)
        else:
            reason = " ".join(resource_sentences) or f"{rname} may be short."
        res_evidence = [
            Evidence(entity_id=resource.id,
                     fact=f"on_hand_quantity={'unknown' if resource.on_hand_quantity is None else resource.on_hand_quantity}"),
            Evidence(entity_id=delivery.id, fact=(f"only {delivery.quantity - moved} of {delivery.quantity} arrive by {orig}; "
                                                  f"{delay_text}")),
        ]
        affected.append(entity(EntityType.RESOURCE, resource.id, verdict, reason, res_evidence,
                               sorted({m for f in res_hits for m in f.missing}), best.breakdown if best else None))
    else:
        cleared.append(CheckedNotAffected(
            entity_type=EntityType.RESOURCE, entity_id=resource.id,
            reason=(f"The delay does not create a shortfall of {rname}." if exposed_jobs
                    else f"No active job needs {rname} while the delayed units are in transit."),
            dependency_paths=res_paths))

    affected.sort(key=lambda e: (_STATUS_RANK[e.impact_status], _TYPE_RANK[e.entity_type], e.entity_id))
    cleared.sort(key=lambda e: (_TYPE_RANK[e.entity_type], e.entity_id))

    fact_list = facts.all()
    problem = fact_list or any(i.severity is not IssueSeverity.INFO for i in issues)
    return ImpactResult(
        disruption_id=inc.id, affected_entities=affected, checked_not_affected=cleared,
        resource_shortfalls=shortfalls, unresolved_facts=fact_list,
        analysis_status=AnalysisStatus.PARTIAL if problem else AnalysisStatus.COMPLETE,
        as_of=as_of, data_issues=issues, config=config)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _reason(value: Any) -> UnresolvedReason:
    try:
        return UnresolvedReason(value)
    except ValueError:
        return UnresolvedReason.UNVERIFIED


def _parse_incident(incident: Any) -> tuple[Optional[NormalizedIncident], Optional[DataIssue]]:
    if isinstance(incident, NormalizedIncident):
        return incident, None
    try:
        return NormalizedIncident.model_validate(incident), None
    except ValidationError as exc:
        return None, DataIssue(code=IssueCode.INVALID_INCIDENT, severity=IssueSeverity.ERROR,
                               message=f"Incident rejected: {summarise(exc)}")


def _incident_id(incident: Any) -> str:
    if isinstance(incident, Mapping) and incident.get("id"):
        return str(incident["id"])
    return "unknown"


def _failed(disruption_id: str, as_of: Optional[date], config: SeverityConfig,
            issues: list[DataIssue], facts: list[UnresolvedFact]) -> ImpactResult:
    return ImpactResult(disruption_id=disruption_id, analysis_status=AnalysisStatus.FAILED, as_of=as_of,
                        data_issues=issues, unresolved_facts=facts, config=config)
