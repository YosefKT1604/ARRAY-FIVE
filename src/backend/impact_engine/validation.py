"""Cross-record validation.

Turns a BusinessSnapshot into a clean BusinessContext. Bad or contradictory
records are skipped or flagged and reported as DataIssues; they never crash the
analysis and are never silently "fixed" with a guess.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .models import (
    BusinessSnapshot,
    Commitment,
    DataIssue,
    Delivery,
    Dependency,
    DependencyType,
    EntityType,
    IssueCode,
    IssueSeverity,
    Job,
    Resource,
    Supplier,
)

# dependency_type -> (required source type, required target type)
_ALLOWED_ENDS = {
    DependencyType.SHIPS: (EntityType.SUPPLIER, EntityType.DELIVERY),
    DependencyType.SUPPLIES: (EntityType.DELIVERY, EntityType.RESOURCE),
    DependencyType.REQUIRES: (EntityType.RESOURCE, EntityType.JOB),
    DependencyType.FULFILS: (EntityType.JOB, EntityType.COMMITMENT),
}


@dataclass
class BusinessContext:
    suppliers: dict[str, Supplier] = field(default_factory=dict)
    resources: dict[str, Resource] = field(default_factory=dict)
    deliveries: dict[str, Delivery] = field(default_factory=dict)
    jobs: dict[str, Job] = field(default_factory=dict)
    commitments: dict[str, Commitment] = field(default_factory=dict)
    dependencies: list[Dependency] = field(default_factory=list)  # cleaned, deduplicated
    # (resource_id, job_id) -> description of the contradictory quantities
    conflicted_requirements: dict[tuple[str, str], str] = field(default_factory=dict)
    issues: list[DataIssue] = field(default_factory=list)


def _issue(code: IssueCode, severity: IssueSeverity, message: str, entity_id: Optional[str] = None) -> DataIssue:
    return DataIssue(code=code, severity=severity, message=message, entity_id=entity_id)


def build_context(snapshot: BusinessSnapshot) -> BusinessContext:
    ctx = BusinessContext(issues=list(snapshot.issues))
    owners: dict[str, str] = {}  # entity id -> kind; entity ids must be globally unique

    def claim(record_id: str, kind: str) -> bool:
        if record_id in owners:
            ctx.issues.append(_issue(
                IssueCode.DUPLICATE_ID, IssueSeverity.ERROR,
                f"{kind} id '{record_id}' is already used by a {owners[record_id]}; this record was skipped.",
                record_id))
            return False
        owners[record_id] = kind
        return True

    for s in snapshot.suppliers:
        if claim(s.id, "supplier"):
            ctx.suppliers[s.id] = s
    for r in snapshot.resources:
        if claim(r.id, "resource"):
            ctx.resources[r.id] = r
    for j in snapshot.jobs:
        if claim(j.id, "job"):
            ctx.jobs[j.id] = j

    for d in snapshot.deliveries:
        if not claim(d.id, "delivery"):
            continue
        bad = [x for x, ok in ((f"supplier '{d.supplier_id}'", d.supplier_id in ctx.suppliers),
                               (f"resource '{d.resource_id}'", d.resource_id in ctx.resources)) if not ok]
        if bad:
            ctx.issues.append(_issue(IssueCode.DANGLING_REFERENCE, IssueSeverity.ERROR,
                                     f"Delivery {d.id} refers to unknown {', '.join(bad)}; skipped.", d.id))
            continue
        ctx.deliveries[d.id] = d

    for c in snapshot.commitments:
        if not claim(c.id, "commitment"):
            continue
        if c.job_id not in ctx.jobs:
            ctx.issues.append(_issue(IssueCode.DANGLING_REFERENCE, IssueSeverity.ERROR,
                                     f"Commitment {c.id} refers to unknown job '{c.job_id}'; skipped.", c.id))
            continue
        ctx.commitments[c.id] = c

    _clean_dependencies(snapshot, ctx)
    _check_dates(ctx)
    return ctx


def _clean_dependencies(snapshot: BusinessSnapshot, ctx: BusinessContext) -> None:
    registries = {
        EntityType.SUPPLIER: ctx.suppliers,
        EntityType.RESOURCE: ctx.resources,
        EntityType.DELIVERY: ctx.deliveries,
        EntityType.JOB: ctx.jobs,
        EntityType.COMMITMENT: ctx.commitments,
    }
    seen_ids: set[str] = set()
    grouped: dict[tuple[DependencyType, str, str], list[Dependency]] = {}

    for d in snapshot.dependencies:
        if d.id in seen_ids:
            ctx.issues.append(_issue(IssueCode.DUPLICATE_ID, IssueSeverity.ERROR,
                                     f"Dependency id '{d.id}' appears more than once; duplicate skipped.", d.id))
            continue
        seen_ids.add(d.id)
        expected = _ALLOWED_ENDS[d.dependency_type]
        if (d.source_type, d.target_type) != expected or d.source_id == d.target_id:
            ctx.issues.append(_issue(
                IssueCode.INVALID_DEPENDENCY, IssueSeverity.ERROR,
                f"Dependency {d.id}: a '{d.dependency_type.value}' edge must go {expected[0].value} -> "
                f"{expected[1].value} between different entities; skipped.", d.id))
            continue
        missing = [f"{t.value} '{i}'" for t, i in ((d.source_type, d.source_id), (d.target_type, d.target_id))
                   if i not in registries[t]]
        if missing:
            ctx.issues.append(_issue(IssueCode.DANGLING_REFERENCE, IssueSeverity.ERROR,
                                     f"Dependency {d.id} refers to unknown {', '.join(missing)}; skipped.", d.id))
            continue
        grouped.setdefault((d.dependency_type, d.source_id, d.target_id), []).append(d)

    for (dep_type, source_id, target_id), group in grouped.items():
        if len(group) == 1:
            ctx.dependencies.append(group[0])
            continue
        quantities = sorted({g.required_quantity for g in group if g.required_quantity is not None})
        dates = sorted({g.required_by for g in group if g.required_by is not None})
        merged = group[0].model_copy(update={
            "required_quantity": quantities[0] if len(quantities) == 1 else None,
            "required_by": dates[0] if len(dates) == 1 else None,
        })
        ctx.dependencies.append(merged)
        if len(quantities) <= 1 and len(dates) <= 1:
            ctx.issues.append(_issue(IssueCode.DUPLICATE_DEPENDENCY, IssueSeverity.INFO,
                                     f"{len(group)} identical '{dep_type.value}' records for {source_id} -> {target_id}; merged.",
                                     source_id))
            continue
        problems = []
        if len(quantities) > 1:
            problems.append(f"required_quantity {' vs '.join(map(str, quantities))}")
            ctx.conflicted_requirements[(source_id, target_id)] = problems[-1]
        if len(dates) > 1:
            problems.append(f"required_by {' vs '.join(map(str, dates))}")
        ctx.issues.append(_issue(IssueCode.CONFLICTING_DEPENDENCY, IssueSeverity.WARNING,
                                 f"Conflicting records for {source_id} -> {target_id}: {'; '.join(problems)}. "
                                 f"Contradictory values are treated as unknown.", target_id))


def _check_dates(ctx: BusinessContext) -> None:
    """Flag date contradictions; the dependency's required_by stays authoritative."""
    needed: dict[str, list[date]] = {}
    for d in ctx.dependencies:
        if d.dependency_type is DependencyType.REQUIRES and d.required_by is not None:
            needed.setdefault(d.target_id, []).append(d.required_by)
            job = ctx.jobs[d.target_id]
            if d.required_by > job.event_date:
                ctx.issues.append(_issue(
                    IssueCode.DATE_CONFLICT, IssueSeverity.WARNING,
                    f"{d.source_id} is required by {d.required_by}, after job {job.id} takes place on {job.event_date}.",
                    job.id))
    for c in ctx.commitments.values():
        if c.required_date is not None and any(dt > c.required_date for dt in needed.get(c.job_id, [])):
            ctx.issues.append(_issue(
                IssueCode.DATE_CONFLICT, IssueSeverity.WARNING,
                f"Commitment {c.id} is due {c.required_date}, before resources for job {c.job_id} are required "
                f"({max(needed[c.job_id])}).", c.id))
