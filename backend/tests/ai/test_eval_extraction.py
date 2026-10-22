"""The extraction evaluation as a test: no case may fill a wrong value or mishandle the fallback."""

from __future__ import annotations

import pytest

from scdc.ai.eval.extraction import PATHS, load_cases, load_snapshot, run_case, with_phones

CASES, DEFAULTS = load_cases()


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case_is_safe(case, path):
    """Zero unsafe values, and the fallback is used exactly when expected (with a warning)."""
    outcome = run_case(case, path, with_phones(load_snapshot(), DEFAULTS.get("supplier_phones", {})), DEFAULTS)
    assert outcome.unsafe == [], outcome.unsafe
    assert outcome.fallback_ok, outcome.fallback_note
