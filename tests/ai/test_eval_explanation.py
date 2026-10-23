"""The explanation evaluation as a test: no planted false item may leak, and integrity must hold."""

from __future__ import annotations

import pytest

from scdc.ai.eval.explanation import load_cases, load_demo, run_case

CASES, CLEAN = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case_is_safe(case):
    """Zero leaks; statuses, missing confirmations, next steps and fallback as expected."""
    outcome = run_case(case, CLEAN, load_demo())
    assert outcome.leaks == [], outcome.leaks
    assert outcome.integrity == [], outcome.integrity
