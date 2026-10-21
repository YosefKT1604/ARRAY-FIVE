"""Plain-text rendering of an ImpactResult (demo command and debugging)."""
from __future__ import annotations

from .models import ImpactResult


def format_report(result: ImpactResult) -> str:
    lines: list[str] = []
    add = lines.append
    add("=" * 74)
    add(f"IMPACT ANALYSIS  disruption={result.disruption_id}  status={result.analysis_status.value.upper()}  as_of={result.as_of}")
    add("=" * 74)

    if result.affected_entities:
        add("\nAFFECTED")
        for e in result.affected_entities:
            sev = f"{e.severity}/10 {e.priority.value}" if e.severity is not None else "no score (needs data)"
            add(f"  [{e.impact_status.value.upper():<14}] {e.entity_type.value} {e.entity_id}   severity {sev}")
            add(f"      path    : {' -> '.join(e.dependency_path)}")
            for p in e.dependency_paths[1:]:
                add(f"                {' -> '.join(p)}")
            add(f"      why     : {e.reason}")
            for ev in e.evidence:
                add(f"      evidence: [{ev.entity_id}] {ev.fact}")
            if e.severity_breakdown:
                b = e.severity_breakdown
                note = f"  (assumed: {', '.join(b.assumed_factors)})" if b.assumed_factors else ""
                add(f"      score   : {b.score} = urgency {b.deadline_urgency} | shortfall {b.resource_shortfall} "
                    f"| importance {b.commitment_importance}{note}")
            for m in e.missing_information:
                add(f"      missing : {m}")
    else:
        add("\nAFFECTED: none")

    if result.resource_shortfalls:
        add("\nRESOURCE SHORTFALLS")
        for s in result.resource_shortfalls:
            add(f"  {s.resource_id} on {s.date}: required {s.required}, available {s.available}, short {s.shortfall}")

    if result.checked_not_affected:
        add("\nCHECKED AND CLEARED")
        for c in result.checked_not_affected:
            add(f"  {c.entity_type.value} {c.entity_id}: {c.reason}")

    if result.unresolved_facts:
        add("\nUNRESOLVED FACTS (could change the result)")
        for f in result.unresolved_facts:
            add(f"  {f.entity_id}.{f.field} [{f.reason.value}]: {f.note}  -> blocks {', '.join(f.affects) or 'n/a'}")

    if result.data_issues:
        add("\nDATA ISSUES")
        for i in result.data_issues:
            add(f"  [{i.severity.value}] {i.code.value}: {i.message}")
    return "\n".join(lines)
