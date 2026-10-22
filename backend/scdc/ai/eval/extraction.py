"""Evaluate Module A (extraction) on fixtures/ai/extraction_cases.json.

Each case runs on two paths: "rules" (no model) and "mock" (rules + the case's scripted model reply).
Every expected field gets one outcome:

    correct        the value matches the expected one (or both are blank)
    safe miss      blank although the value was knowable: the owner is asked one extra question
    unsafe         filled with a wrong value: the owner would be misled  <- must be zero

The evaluation fails (exit code 1, and in pytest) on any unsafe value or a wrong fallback.
Accuracy, safe misses and blank reasons are reported only.

Run from backend/:  .\\.venv\\Scripts\\python.exe -m scdc.ai.eval.extraction
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..adapter import MockAdapter, ModelTimeoutError, ModelUnavailableError
from ..extraction import extract_incident
from ..schemas import BusinessSnapshot

REPO_ROOT = Path(__file__).resolve().parents[4]
CASES_PATH = REPO_ROOT / "fixtures" / "ai" / "extraction_cases.json"
SEED_PATH = REPO_ROOT / "fixtures" / "demo" / "seed.json"
PATHS = ("rules", "mock")
MODEL_ERRORS = {"timeout": ModelTimeoutError, "unavailable": ModelUnavailableError}


@dataclass
class CaseOutcome:
    """The score of one case on one path."""

    case_id: str
    category: str
    path: str
    correct: list[str] = field(default_factory=list)
    safe_misses: list[str] = field(default_factory=list)
    unsafe: list[str] = field(default_factory=list)          # "field: got X, expected Y"
    reason_mismatches: list[str] = field(default_factory=list)
    reasons_checked: int = 0
    fallback_ok: bool = True
    fallback_note: str = ""

    @property
    def passed(self) -> bool:
        """A case passes when nothing unsafe was filled and the fallback behaved as expected."""
        return not self.unsafe and self.fallback_ok


# --- Loading ------------------------------------------------------------------------


def load_cases(path: Path = CASES_PATH) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read the evaluation cases and their defaults."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["cases"], data.get("defaults", {})


def load_snapshot(path: Path = SEED_PATH) -> BusinessSnapshot:
    """Read the demo business data the cases refer to."""
    return BusinessSnapshot.model_validate(json.loads(path.read_text(encoding="utf-8")))


def scripted_reply(case: dict[str, Any]) -> Any:
    """The MockAdapter reply for a case: a JSON reading, raw text, or an exception to raise."""
    if "model_error" in case:
        return MODEL_ERRORS[case["model_error"]](f"scripted {case['model_error']}")
    if "model_reply_text" in case:
        return case["model_reply_text"]
    return case["model_reply"]


# --- Scoring ------------------------------------------------------------------------


def run_case(case: dict[str, Any], path: str, snapshot: BusinessSnapshot, defaults: dict[str, Any]) -> CaseOutcome:
    """Run one case on one path ("rules" or "mock") and score every expected field."""
    adapter = MockAdapter({"extract_incident": scripted_reply(case)}) if path == "mock" else None
    reported_at = datetime.fromisoformat(case.get("reported_at", defaults["reported_at"]))
    result = extract_incident(case["message"], snapshot, reported_at, sender=case.get("sender"),
                              from_number=case.get("from_number"), contact_name=case.get("contact_name"), adapter=adapter)

    outcome = CaseOutcome(case["id"], case["category"], path)
    got = result.draft_incident.model_dump(mode="json")
    for name, expected in case["expected"].items():
        actual = got[name]
        if actual == expected:
            outcome.correct.append(name)
        elif actual is None:
            outcome.safe_misses.append(name)
        else:
            outcome.unsafe.append(f"{name}: got {actual}, expected {expected}")

    reasons = {u.field: u.reason.value for u in result.unresolved_fields}
    for name, reason in case.get("expected_blank", {}).items():
        outcome.reasons_checked += 1
        if reasons.get(name) != reason:
            outcome.reason_mismatches.append(f"{name}: got {reasons.get(name)}, expected {reason}")

    should_fall_back = path == "rules" or case.get("expected_fallback", False)
    if result.fallback_used != should_fall_back:
        outcome.fallback_ok = False
        outcome.fallback_note = f"fallback_used={result.fallback_used}, expected {should_fall_back}"
    elif should_fall_back and path == "mock" and not result.warnings:
        outcome.fallback_ok = False
        outcome.fallback_note = "fell back without a warning"
    return outcome


def with_phones(snapshot: BusinessSnapshot, phones: dict[str, str]) -> BusinessSnapshot:
    """A copy of the business data with the eval's supplier phone numbers added (fixtures/demo is not changed)."""
    copy = snapshot.model_copy(deep=True)
    for supplier in copy.suppliers:
        supplier.phone = phones.get(supplier.id, supplier.phone)
    return copy


def run_all(cases_path: Path = CASES_PATH) -> list[CaseOutcome]:
    """Run every case on every path."""
    cases, defaults = load_cases(cases_path)
    snapshot = with_phones(load_snapshot(), defaults.get("supplier_phones", {}))
    return [run_case(case, path, snapshot, defaults) for case in cases for path in PATHS]


def summarise(outcomes: list[CaseOutcome], path: str) -> dict[str, Any]:
    """Totals for one path: field accuracy, safe misses, unsafe values, reason matches, fallback failures."""
    rows = [o for o in outcomes if o.path == path]
    correct = sum(len(o.correct) for o in rows)
    total = correct + sum(len(o.safe_misses) + len(o.unsafe) for o in rows)
    checked = sum(o.reasons_checked for o in rows)
    return {
        "path": path,
        "cases": len(rows),
        "field_accuracy": correct / total if total else 0.0,
        "correct": correct,
        "fields": total,
        "safe_misses": sum(len(o.safe_misses) for o in rows),
        "unsafe": sum(len(o.unsafe) for o in rows),
        "reasons_matched": checked - sum(len(o.reason_mismatches) for o in rows),
        "reasons_checked": checked,
        "fallback_failures": sum(not o.fallback_ok for o in rows),
    }


# --- Command line -----------------------------------------------------------------------


def print_report(outcomes: list[CaseOutcome]) -> None:
    """Print one line per case and path, then the totals per path."""
    print(f"{'case':5} {'category':20} {'path':5} {'correct':>7}  safe misses / problems")
    for o in outcomes:
        total = len(o.correct) + len(o.safe_misses) + len(o.unsafe)
        problems = [f"UNSAFE {u}" for u in o.unsafe] + ([f"FALLBACK {o.fallback_note}"] if not o.fallback_ok else [])
        notes = ", ".join(problems + o.safe_misses + [f"reason {r}" for r in o.reason_mismatches]) or "-"
        print(f"{o.case_id:5} {o.category:20} {o.path:5} {len(o.correct):>3}/{total:<3}  {notes}")
    print()
    for path in PATHS:
        s = summarise(outcomes, path)
        print(f"[{path}] field accuracy {s['field_accuracy']:.1%} ({s['correct']}/{s['fields']}), "
              f"safe misses {s['safe_misses']}, UNSAFE {s['unsafe']}, "
              f"blank reasons {s['reasons_matched']}/{s['reasons_checked']}, fallback failures {s['fallback_failures']}")


def main() -> int:
    """Run the evaluation, print the report, and return 1 if any case failed."""
    outcomes = run_all()
    print_report(outcomes)
    return 0 if all(o.passed for o in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
