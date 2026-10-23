"""Tests that Person 2's real contract objects convert into the AI module's shapes, and work end to end."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

import contracts
from app.db.seed import load_fixture
from app.services.impact import analyze_impact
from app.services.recovery import generate_plans
from app.services.snapshot import build_snapshot
from scdc.ai.bridge import ai_impact, ai_incident, ai_plans, ai_snapshot
from scdc.ai.explanation import explain
from scdc.ai.extraction import extract_incident
from scdc.ai.schemas import UnresolvedReason

from .conftest import DEMO_FIXTURES, DEMO_MESSAGE


@pytest.fixture
def p2(session_factory):
    """P2's own objects for the demo: snapshot from the seeded database, incident, stub impact and plans."""
    data = json.loads((DEMO_FIXTURES / "incident.json").read_text(encoding="utf-8"))
    incident = contracts.NormalizedIncident.model_validate(data["expected_normalized_incident"])
    with session_factory() as session:
        load_fixture(session)
        snapshot = build_snapshot(session, incident)
    impact = analyze_impact(incident, snapshot)
    return {"incident": incident, "snapshot": snapshot, "impact": impact,
            "plans": generate_plans(incident, snapshot, impact)}


def test_snapshot_from_database_converts(p2):
    """The snapshot P2 builds from the database keeps its records, dates and exact money amounts."""
    snapshot = ai_snapshot(p2["snapshot"])
    assert [s.id for s in snapshot.suppliers] == [s.id for s in p2["snapshot"].suppliers]
    assert [d.expected_date for d in snapshot.deliveries] == [d.expected_date for d in p2["snapshot"].deliveries]
    assert snapshot.supplier_offerings[1].unit_cost.amount == Decimal("4.00")


def test_incident_impact_and_plans_convert(p2):
    """Incident, impact and plans keep their IDs, statuses and order."""
    incident = ai_incident(p2["incident"])
    impact = ai_impact(p2["impact"])
    plans = ai_plans(p2["plans"])
    assert (incident.id, incident.quantity_affected) == (p2["incident"].id, 20)
    assert [e.entity_id for e in impact.affected_entities] == [e.entity_id for e in p2["impact"].affected_entities]
    assert [p.id for p in plans] == [p.id for p in p2["plans"]]
    assert [p.validation.status.value for p in plans] == [p.validation.status.value for p in p2["plans"]]


def test_explanation_works_on_converted_objects(p2):
    """Module B runs on P2's objects (no model: the template explanation) and mentions every plan."""
    explanation = explain(ai_incident(p2["incident"]), ai_impact(p2["impact"]), ai_plans(p2["plans"]),
                          snapshot=ai_snapshot(p2["snapshot"]))
    assert explanation.generated_by == "template"
    assert sorted(c.plan_id for c in explanation.plan_comparisons) == sorted(p.id for p in p2["plans"])


def test_sender_contact_reference_identifies_supplier_from_database(p2):
    """The frontend's `from_contact` (passed as `sender=`) matches Maju's contact_reference in P2's data."""
    maju = next(s for s in p2["snapshot"].suppliers if s.id == "S-01")
    result = extract_incident(DEMO_MESSAGE, ai_snapshot(p2["snapshot"]), datetime(2026, 10, 20, 9, 0, tzinfo=UTC),
                              sender=maju.contact_reference)
    assert result.draft_incident.supplier_id == "S-01"


def test_empty_supplier_notes_and_job_description_become_empty_text(p2):
    """P2 allows None for a supplier's notes and a job's description; we read them as ""."""
    snapshot = p2["snapshot"]
    snapshot = snapshot.model_copy(update={
        "suppliers": [s.model_copy(update={"reliability_notes": None}) for s in snapshot.suppliers],
        "jobs": [j.model_copy(update={"description": None}) for j in snapshot.jobs],
    })
    converted = ai_snapshot(snapshot)
    assert {s.reliability_notes for s in converted.suppliers} == {""}
    assert {j.description for j in converted.jobs} == {""}


def test_unresolved_field_with_empty_note_and_number_value(p2):
    """P2 allows `note=None` and any `raw_value`; we read them as "" and as text ("20")."""
    unresolved = contracts.UnresolvedField(field="quantity_affected", reason=contracts.UnresolvedReason.AMBIGUOUS,
                                           raw_value=20, note=None)
    incident = p2["incident"].model_copy(update={"unresolved_fields": [unresolved]})
    field = ai_incident(incident).unresolved_fields[0]
    assert (field.reason, field.raw_value, field.note) == (UnresolvedReason.AMBIGUOUS, "20", "")
