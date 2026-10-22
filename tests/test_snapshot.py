from datetime import date

from app.db.seed import load_fixture
from app.services.snapshot import build_snapshot
from contracts import NormalizedIncident

INCIDENT = NormalizedIncident(
    id="D-001", type="supplier_delay", source="form", supplier_id="S-01", resource_id="R-01",
    delivery_id="DL-01", quantity_affected=20, original_arrival_date=date(2026, 10, 21),
    new_arrival_date=date(2026, 10, 23), description="Late chairs", reported_at="2026-10-20T10:15:00+08:00",
)


def test_snapshot_contains_all_business_records(session_factory):
    with session_factory() as session:
        load_fixture(session)
        snapshot = build_snapshot(session, INCIDENT)

    assert snapshot.business.id == "B-01"
    assert [job.id for job in snapshot.jobs] == ["J-01", "J-02", "J-03"]
    assert [commitment.id for commitment in snapshot.commitments] == ["CM-01", "CM-02", "CM-03"]
    assert len(snapshot.dependencies) == 9
    assert snapshot.as_of.tzinfo is not None

def test_snapshot_keeps_offering_cost_as_money(session_factory):
    with session_factory() as session:
        load_fixture(session)
        snapshot = build_snapshot(session, INCIDENT)

    offering = next(o for o in snapshot.supplier_offerings if o.supplier_id == "S-02")
    assert str(offering.unit_cost.amount) == "4.00"