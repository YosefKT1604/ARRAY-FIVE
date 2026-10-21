import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from contracts import BusinessSnapshot, ImpactResult, NormalizedIncident, RecoveryPlan

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "demo"

def load(name: str) -> dict:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    data.pop("_note", None)
    return data

def test_incident_fixture_matches_contract():
    incident = NormalizedIncident.model_validate(load("incident.json")["expected_normalized_incident"])
    assert incident.quantity_affected == 20

def test_seed_fixture_matches_snapshot_contract():
    seed = load("seed.json")
    seed.pop("users")  # users are not part of the snapshot
    snapshot = BusinessSnapshot.model_validate(seed)
    assert len(snapshot.dependencies) == 9

def test_impact_fixture_matches_contract():
    impact = ImpactResult.model_validate(load("expected_impact.json"))
    assert impact.resource_shortfalls[0].shortfall == 20

def test_plan_fixtures_match_contract():
    plans = [RecoveryPlan.model_validate(plan) for plan in load("expected_plans.json")["plans"]]
    assert [plan.validation.status for plan in plans] == ["feasible", "infeasible", "needs_confirmation"]

def test_contracts_reject_unknown_fields_and_values():
    incident = load("incident.json")["expected_normalized_incident"]
    with pytest.raises(ValidationError):
        NormalizedIncident.model_validate({**incident, "qty": 20})
    with pytest.raises(ValidationError):
        NormalizedIncident.model_validate({**incident, "type": "truck_breakdown"})