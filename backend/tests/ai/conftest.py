"""Shared pytest fixtures for the AI module tests. Nothing here needs a model or an API key."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from scdc.ai.schemas import BusinessSnapshot, ImpactResult, NormalizedIncident, RecoveryPlan

DEMO_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "demo"
REPORTED_ON = date(2026, 10, 20)  # Tuesday: the demo's report day
DEMO_MESSAGE = ("Boss, sorry ya. Our chair delivery for tomorrow will be late. We can only send 20 chairs "
                "tomorrow, the remaining 20 chairs we deliver on Friday.")


@pytest.fixture
def snapshot() -> BusinessSnapshot:
    """The team's demo business data (fixtures/demo/seed.json)."""
    return BusinessSnapshot.model_validate(_demo("seed.json"))


def _demo(name: str) -> dict:
    """Read one demo fixture file as JSON."""
    return json.loads((DEMO_FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def incident() -> NormalizedIncident:
    """The demo's confirmed incident D-001 (fixtures/demo/incident.json)."""
    return NormalizedIncident.model_validate(_demo("incident.json")["expected_normalized_incident"])


@pytest.fixture
def impact() -> ImpactResult:
    """Person 3's expected impact for the demo (fixtures/demo/expected_impact.json)."""
    return ImpactResult.model_validate(_demo("expected_impact.json"))


@pytest.fixture
def plans() -> list[RecoveryPlan]:
    """Person 4's expected plans for the demo: RP-001 feasible, RP-002 infeasible, RP-003 needs confirmation."""
    return [RecoveryPlan.model_validate(p) for p in _demo("expected_plans.json")["plans"]]
