"""The drafts evaluation as a test: no bad polish may reach a draft, and integrity must hold."""

from __future__ import annotations

import pytest

from scdc.ai.eval.drafts import load_cases, load_demo, run_case

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case_is_safe(case):
    """Zero leaks; IDs, recipients, placeholders, status, generated_by, approval and fallback as expected."""
    outcome = run_case(case, *load_demo())
    assert outcome.result != "leak", case["category"]
    assert outcome.integrity == [], outcome.integrity
