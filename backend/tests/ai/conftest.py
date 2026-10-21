"""Shared pytest fixtures for the AI module tests. Nothing here needs a model or an API key."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from scdc.ai.schemas import BusinessSnapshot

DEMO_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "demo"
REPORTED_ON = date(2026, 10, 20)  # Tuesday: the demo's report day
DEMO_MESSAGE = ("Boss, sorry ya. Our chair delivery for tomorrow will be late. We can only send 20 chairs "
                "tomorrow, the remaining 20 chairs we deliver on Friday.")


@pytest.fixture
def snapshot() -> BusinessSnapshot:
    """The team's demo business data (fixtures/demo/seed.json)."""
    return BusinessSnapshot.model_validate(json.loads((DEMO_FIXTURES / "seed.json").read_text(encoding="utf-8")))
