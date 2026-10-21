"""Tests that the schemas accept the team's demo data and reject bad data."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from scdc.ai.schemas import (
    BusinessSnapshot,
    DraftIncident,
    ExtractionResult,
    Money,
    UnresolvedField,
    UnresolvedReason,
)

DEMO = Path(__file__).resolve().parents[3] / "fixtures" / "demo"


def load(name: str) -> dict:
    """Read one of the shared demo fixture files."""
    return json.loads((DEMO / name).read_text(encoding="utf-8"))


def test_demo_seed_loads_as_snapshot():
    """The shared seed data fits BusinessSnapshot; extra keys like `users` are ignored."""
    snapshot = BusinessSnapshot.model_validate(load("seed.json"))
    assert [s.id for s in snapshot.suppliers] == ["S-01", "S-02", "S-03"]
    assert snapshot.deliveries[0].expected_date.isoformat() == "2026-10-21"
    assert snapshot.supplier_offerings[1].unit_cost.amount == Decimal("4.00")


def test_money_is_exact_decimal_and_written_as_two_decimal_string():
    """Money from the seed is a Decimal: exact maths, and JSON output like "80.00"."""
    snapshot = BusinessSnapshot.model_validate(load("seed.json"))
    unit = snapshot.supplier_offerings[1].unit_cost.amount  # Cahaya, RM 4.00 per chair
    assert unit == Decimal("4.00")
    assert unit * 20 == Decimal("80.00")
    assert Money(amount=unit * 20).model_dump(mode="json") == {"amount": "80.00", "currency": "MYR"}


@pytest.mark.parametrize("raw, written", [("2.675", "2.68"), ("1.005", "1.01"), ("56", "56.00"), ("0.1", "0.10")])
def test_money_rounds_half_up_to_two_places(raw, written):
    """Amounts are written with 2 decimals, rounding half up (where float formatting would get 2.67)."""
    assert Money(amount=raw).model_dump(mode="json")["amount"] == written


def test_demo_expected_incident_fits_draft_incident():
    """The incident the team agreed on in Phase 1 is a valid DraftIncident."""
    incident = DraftIncident.model_validate(load("incident.json")["expected_normalized_incident"])
    assert incident.quantity_affected == 20
    assert incident.new_arrival_date.isoformat() == "2026-10-23"


@pytest.mark.parametrize("bad", [
    {"quantity_affected": 0},              # must be at least 1
    {"quantity_affected": "twenty"},       # must be a number
    {"type": "earthquake"},                # not a known disruption type
    {"new_arrival_date": "Friday"},        # dates must be real dates, not phrases
    {"suplier_id": "S-01"},                # typo: unknown keys are rejected
])
def test_draft_incident_rejects_bad_values(bad):
    """Wrong types, unknown enum values and misspelled keys fail validation."""
    with pytest.raises(ValidationError):
        DraftIncident.model_validate(bad)


def test_unresolved_field_only_accepts_known_fields_and_reasons():
    """Unresolved entries must name a real incident field and a known reason."""
    UnresolvedField(field="quantity_affected", reason=UnresolvedReason.MISSING)
    with pytest.raises(ValidationError):
        UnresolvedField(field="colour", reason="missing")
    with pytest.raises(ValidationError):
        UnresolvedField(field="supplier_id", reason="probably")


def test_extraction_result_requires_provenance():
    """An ExtractionResult must say how it was produced and whether the fallback was used."""
    with pytest.raises(ValidationError):
        ExtractionResult(draft_incident=DraftIncident(), needs_clarification=True)
    result = ExtractionResult(draft_incident=DraftIncident(), needs_clarification=True,
                              generated_by="template", fallback_used=True)
    assert result.model_dump(mode="json")["draft_incident"]["source"] == "message"
