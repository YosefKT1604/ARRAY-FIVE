"""Evaluate Module B (explanations) on fixtures/ai/explanation_cases.json.

Each case is a scripted model reply on the demo data, with some planted false items (`bad_items`).
Every item of the reply gets one outcome:

    caught        a bad item was replaced or dropped
    leak          a bad item reached the final explanation          <- must be zero
    kept          a good item was used
    false alarm   a good item was replaced anyway (safe, but lowers the model's value)

Integrity (must always hold): plan statuses, missing confirmations and next steps equal the
template's, and the fallback is used exactly when expected.

Run from backend/:  .\\.venv\\Scripts\\python.exe -m scdc.ai.eval.explanation
"""

from __future__ import annotations

import copy
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..adapter import MockAdapter, ModelTimeoutError, ModelUnavailableError
from ..explanation import explain
from ..explanation_template import build_template, template_explanation
from ..schemas import BusinessSnapshot, Explanation, ImpactResult, NormalizedIncident, RecoveryPlan

REPO_ROOT = Path(__file__).resolve().parents[4]
CASES_PATH = REPO_ROOT / "fixtures" / "ai" / "explanation_cases.json"
DEMO_DIR = REPO_ROOT / "fixtures" / "demo"
MODEL_ERRORS = {"timeout": ModelTimeoutError, "unavailable": ModelUnavailableError}


@dataclass
class DemoData:
    """The demo incident, impact, plans and business data every case runs on."""

    incident: NormalizedIncident
    impact: ImpactResult
    plans: list[RecoveryPlan]
    snapshot: BusinessSnapshot


@dataclass
class CaseOutcome:
    """The score of one case."""

    case_id: str
    category: str
    caught: list[str] = field(default_factory=list)
    leaks: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    false_alarms: list[str] = field(default_factory=list)
    integrity: list[str] = field(default_factory=list)   # broken rules, e.g. "next steps changed"
    removed: int = 0

    @property
    def passed(self) -> bool:
        """A case passes when nothing leaked and every integrity rule held."""
        return not self.leaks and not self.integrity


# --- Loading ------------------------------------------------------------------------------


def _read(path: Path) -> Any:
    """Read a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_demo() -> DemoData:
    """Read the demo data from fixtures/demo/."""
    return DemoData(
        incident=NormalizedIncident.model_validate(_read(DEMO_DIR / "incident.json")["expected_normalized_incident"]),
        impact=ImpactResult.model_validate(_read(DEMO_DIR / "expected_impact.json")),
        plans=[RecoveryPlan.model_validate(p) for p in _read(DEMO_DIR / "expected_plans.json")["plans"]],
        snapshot=BusinessSnapshot.model_validate(_read(DEMO_DIR / "seed.json")),
    )


def load_cases(path: Path = CASES_PATH) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read the cases and the clean replies they are based on."""
    data = _read(path)
    return data["cases"], data["clean_replies"]


# --- Building a case's reply --------------------------------------------------------------------


def _set_item(reply: dict[str, Any], path: str, text: str) -> None:
    """Put `text` at a path in a reply, replacing the item there or adding it."""
    parts = path.split("/")
    if path == "summary":
        reply["summary"] = text
    elif parts[0] == "impact":
        items = reply.setdefault("impact_explanations", [])
        items[:] = [i for i in items if i["entity_id"] != parts[1]] + [{"entity_id": parts[1], "text": text}]
    elif len(parts) == 1:  # a whole invented plan
        reply.setdefault("plan_comparisons", []).append({"plan_id": path, "benefits": [{"source": "cost", "text": text}]})
    else:
        plan_id, kind, key = parts
        comparisons = reply.setdefault("plan_comparisons", [])
        plan = next((c for c in comparisons if c["plan_id"] == plan_id), None)
        if plan is None:
            plan = {"plan_id": plan_id}
            comparisons.append(plan)
        items = plan.setdefault(kind, [])
        items[:] = [i for i in items if i["source"] != key] + [{"source": key, "text": text}]


def build_reply(case: dict[str, Any], clean: dict[str, Any]) -> dict[str, Any] | None:
    """The case's model reply as JSON data (None for raw-text or error cases)."""
    if "model_reply" in case:
        return case["model_reply"]
    if "based_on" not in case:
        return None
    reply = copy.deepcopy(clean[case["based_on"]])
    for path, text in case.get("override", {}).items():
        _set_item(reply, path, text)
    return reply


def scripted(case: dict[str, Any], reply: dict[str, Any] | None) -> Any:
    """What MockAdapter should give: the reply, raw text, or an exception."""
    if "model_error" in case:
        return MODEL_ERRORS[case["model_error"]](f"scripted {case['model_error']}")
    if "model_reply_text" in case:
        return case["model_reply_text"]
    return reply


# --- Reading items by path ------------------------------------------------------------------------


def reply_items(reply: dict[str, Any] | None) -> dict[str, str]:
    """Every item of a model reply, by path."""
    if not reply:
        return {}
    items = {"summary": reply["summary"]} if "summary" in reply else {}
    items.update({f"impact/{i['entity_id']}": i["text"] for i in reply.get("impact_explanations", [])})
    for plan in reply.get("plan_comparisons", []):
        for kind in ("benefits", "limitations"):
            items.update({f"{plan['plan_id']}/{kind}/{i['source']}": i["text"] for i in plan.get(kind, [])})
    return items


def final_items(result: Explanation, demo: DemoData) -> dict[str, str]:
    """Every item of the final explanation, by path (benefits/limitations keyed via the template's order)."""
    keys = {c.plan_id: c for c in build_template(demo.incident, demo.impact, demo.plans, snapshot=demo.snapshot)
            .raw.plan_comparisons}
    items = {"summary": result.summary}
    items.update({f"impact/{i.entity_id}": i.text.split(": ", 1)[1] for i in result.impact_explanations})
    for comparison in result.plan_comparisons:
        template = keys[comparison.plan_id]
        for kind in ("benefits", "limitations"):
            sources = [i.source for i in getattr(template, kind)]
            items.update({f"{comparison.plan_id}/{kind}/{s}": t for s, t in zip(sources, getattr(comparison, kind))})
    return items


# --- Scoring --------------------------------------------------------------------------------------


def _is_bad(path: str, bad_items: list[str]) -> bool:
    """Is this reply item one of the planted bad ones (a whole invented plan covers its items)?"""
    return any(path == bad or path.startswith(bad + "/") for bad in bad_items)


def run_case(case: dict[str, Any], clean: dict[str, Any], demo: DemoData) -> CaseOutcome:
    """Run one case and score every item of its reply, plus the integrity rules."""
    reply = build_reply(case, clean)
    adapter = MockAdapter({"explain": scripted(case, reply)})
    result = explain(demo.incident, demo.impact, demo.plans, snapshot=demo.snapshot, adapter=adapter)
    template = template_explanation(demo.incident, demo.impact, demo.plans, snapshot=demo.snapshot)

    outcome = CaseOutcome(case["id"], case["category"], removed=result.unsupported_claims_removed)
    final = final_items(result, demo)
    shown = set(final.values())
    for path, text in reply_items(reply).items():
        if _is_bad(path, case["bad_items"]):
            # A bad item leaks if it is shown at its own place; an invented item (no place) if it is shown anywhere.
            leaked = final.get(path) == text if path in final else text in shown
            (outcome.leaks if leaked else outcome.caught).append(path)
        else:
            (outcome.kept if final.get(path) == text else outcome.false_alarms).append(path)

    statuses = [(c.plan_id, c.validation_status) for c in result.plan_comparisons]
    if statuses != [(c.plan_id, c.validation_status) for c in template.plan_comparisons]:
        outcome.integrity.append("plan statuses changed")
    if result.missing_confirmations != template.missing_confirmations:
        outcome.integrity.append("missing confirmations changed")
    if result.next_steps != template.next_steps:
        outcome.integrity.append("next steps changed")
    if case.get("expected_fallback", False):
        if result != template:
            outcome.integrity.append("expected the template fallback")
    elif result.fallback_used:
        outcome.integrity.append(f"fell back unexpectedly (generated_by={result.generated_by})")
    return outcome


def run_all(cases_path: Path = CASES_PATH) -> list[CaseOutcome]:
    """Run every case."""
    cases, clean = load_cases(cases_path)
    demo = load_demo()
    return [run_case(case, clean, demo) for case in cases]


def summarise(outcomes: list[CaseOutcome]) -> dict[str, Any]:
    """Totals: bad items caught / leaked, good items kept / falsely replaced, integrity failures."""
    caught, leaks = sum(len(o.caught) for o in outcomes), sum(len(o.leaks) for o in outcomes)
    kept, alarms = sum(len(o.kept) for o in outcomes), sum(len(o.false_alarms) for o in outcomes)
    return {
        "cases": len(outcomes),
        "bad_items": caught + leaks, "caught": caught, "leaks": leaks,
        "good_items": kept + alarms, "kept": kept, "false_alarms": alarms,
        "integrity_failures": sum(len(o.integrity) for o in outcomes),
        "unsupported_claims_removed": sum(o.removed for o in outcomes),
    }


# --- Command line -----------------------------------------------------------------------------------


def print_report(outcomes: list[CaseOutcome]) -> None:
    """Print one line per case, then the totals."""
    print(f"{'case':5} {'category':22} {'caught':>6} {'kept':>5}  problems")
    for o in outcomes:
        problems = ([f"LEAK {p}" for p in o.leaks] + [f"INTEGRITY {p}" for p in o.integrity]
                    + [f"false alarm {p}" for p in o.false_alarms])
        print(f"{o.case_id:5} {o.category:22} {len(o.caught):>6} {len(o.kept):>5}  {', '.join(problems) or '-'}")
    s = summarise(outcomes)
    print(f"\nbad items caught {s['caught']}/{s['bad_items']}, LEAKS {s['leaks']}; "
          f"good items kept {s['kept']}/{s['good_items']}, false alarms {s['false_alarms']}; "
          f"integrity failures {s['integrity_failures']}; unsupported_claims_removed total {s['unsupported_claims_removed']}")


def main() -> int:
    """Run the evaluation, print the report, and return 1 if any case failed."""
    outcomes = run_all()
    print_report(outcomes)
    return 0 if all(o.passed for o in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
