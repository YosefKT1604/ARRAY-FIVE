"""Evaluate Module C (draft messages) on fixtures/ai/draft_cases.json.

Each case drafts the messages for one plan on the demo data, with a scripted polish from the model:

    caught        a bad polish was rejected (the template text was kept)
    leak          a bad polish reached the draft                       <- must be zero
    kept          a good polish was used
    false alarm   a good polish was rejected (safe, but loses the polish)

Integrity (must always hold): every draft keeps the template's ID, recipient, placeholders and
status "draft"; `generated_by` says "model:..." exactly when the polish was used; a plan that is
not approved is refused; when the model fails, the template drafts are returned unchanged.

Run from backend/:  .\\.venv\\Scripts\\python.exe -m scdc.ai.eval.drafts
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..adapter import MockAdapter, ModelTimeoutError, ModelUnavailableError
from ..drafts import DraftNotAllowedError, draft_messages
from ..drafts_template import template_drafts
from ..schemas import BusinessSnapshot, NormalizedIncident, RecoveryAction, RecoveryPlan

REPO_ROOT = Path(__file__).resolve().parents[5]
CASES_PATH = REPO_ROOT / "fixtures" / "ai" / "draft_cases.json"
DEMO_DIR = REPO_ROOT / "fixtures" / "demo"
MODEL_ERRORS = {"timeout": ModelTimeoutError, "unavailable": ModelUnavailableError}


@dataclass
class CaseOutcome:
    """The score of one case."""

    case_id: str
    category: str
    result: str = ""                                     # caught | leak | kept | false alarm | fallback | refused
    integrity: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """A case passes when nothing leaked and every integrity rule held."""
        return self.result != "leak" and not self.integrity


def _read(path: Path) -> Any:
    """Read a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_cases(path: Path = CASES_PATH) -> list[dict[str, Any]]:
    """Read the cases."""
    return _read(path)["cases"]


def load_demo() -> tuple[NormalizedIncident, list[RecoveryPlan], BusinessSnapshot]:
    """The demo incident, plans and business data."""
    return (NormalizedIncident.model_validate(_read(DEMO_DIR / "incident.json")["expected_normalized_incident"]),
            [RecoveryPlan.model_validate(p) for p in _read(DEMO_DIR / "expected_plans.json")["plans"]],
            BusinessSnapshot.model_validate(_read(DEMO_DIR / "seed.json")))


def case_plan(case: dict[str, Any], plans: list[RecoveryPlan]) -> RecoveryPlan:
    """The case's plan: a copy of a demo plan, approved unless the case says not, with its actions replaced if given."""
    plan = next(p for p in plans if p.id == case["plan"]).model_copy(deep=True)
    if case.get("approved", True):
        plan.status = "approved"
    if "actions" in case:
        plan.actions = [RecoveryAction.model_validate(a) for a in case["actions"]]
    return plan


def scripted(case: dict[str, Any]) -> Any:
    """What MockAdapter should give: a polish, raw text, or an exception."""
    if "model_error" in case:
        return MODEL_ERRORS[case["model_error"]](f"scripted {case['model_error']}")
    if "model_reply_text" in case:
        return case["model_reply_text"]
    return {"body": case["polish"]}


def run_case(case: dict[str, Any], incident: NormalizedIncident, plans: list[RecoveryPlan],
             snapshot: BusinessSnapshot) -> CaseOutcome:
    """Draft one case's plan with its scripted polish, and score the outcome and the integrity rules."""
    outcome = CaseOutcome(case["id"], case["category"])
    plan = case_plan(case, plans)
    adapter = MockAdapter({"*": scripted(case)})
    try:
        drafts = draft_messages(plan, incident, snapshot, adapter=adapter)
    except DraftNotAllowedError:
        outcome.result = "refused"
        if case.get("approved", True):
            outcome.integrity.append("refused an approved plan")
        return outcome
    if not case.get("approved", True):
        outcome.integrity.append("drafted for a plan that is not approved")

    templates = template_drafts(plan, incident, snapshot)
    for draft, template in zip(drafts, templates):
        same = ("id", "plan_id", "recipient_type", "recipient_id", "placeholders", "status")
        outcome.integrity += [f"{draft.id}: {name} changed" for name in same
                              if getattr(draft, name) != getattr(template, name)]
        used = draft.body != template.body
        if used != draft.generated_by.startswith("model:"):
            outcome.integrity.append(f"{draft.id}: generated_by={draft.generated_by} does not match the text")
    if len(drafts) != len(templates):
        outcome.integrity.append("number of drafts changed")

    if "polish" not in case:
        outcome.result = "fallback"
        if drafts != templates:
            outcome.integrity.append("expected the template drafts unchanged")
    else:
        used = any(d.body == case["polish"] for d in drafts)
        outcome.result = ("leak" if used else "caught") if case["bad"] else ("kept" if used else "false alarm")
    return outcome


def run_all(cases_path: Path = CASES_PATH) -> list[CaseOutcome]:
    """Run every case."""
    incident, plans, snapshot = load_demo()
    return [run_case(case, incident, plans, snapshot) for case in load_cases(cases_path)]


def summarise(outcomes: list[CaseOutcome]) -> dict[str, int]:
    """Totals per outcome, plus integrity failures."""
    counts = {name: sum(o.result == name for o in outcomes)
              for name in ("caught", "leak", "kept", "false alarm", "fallback", "refused")}
    counts["integrity_failures"] = sum(len(o.integrity) for o in outcomes)
    return counts


def print_report(outcomes: list[CaseOutcome]) -> None:
    """Print one line per case, then the totals."""
    print(f"{'case':5} {'category':24} {'result':12} problems")
    for o in outcomes:
        problems = [f"INTEGRITY {p}" for p in o.integrity] + (["LEAK"] if o.result == "leak" else [])
        print(f"{o.case_id:5} {o.category:24} {o.result:12} {', '.join(problems) or '-'}")
    s = summarise(outcomes)
    print(f"\nbad polishes caught {s['caught']}/{s['caught'] + s['leak']}, LEAKS {s['leak']}; "
          f"good polishes kept {s['kept']}/{s['kept'] + s['false alarm']}, false alarms {s['false alarm']}; "
          f"fallbacks {s['fallback']}, refused {s['refused']}; integrity failures {s['integrity_failures']}")


def main() -> int:
    """Run the evaluation, print the report, and return 1 if any case failed."""
    outcomes = run_all()
    print_report(outcomes)
    return 0 if all(o.passed for o in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
