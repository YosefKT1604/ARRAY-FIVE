"""Team demo fixtures (fixtures/demo/) and named variations used by the demo command and tests.

Set SCDC_FIXTURES to point at a different fixtures/demo directory (e.g. inside the team repo).
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Callable

FIXTURE_DIR = Path(os.environ.get("SCDC_FIXTURES") or Path(__file__).resolve().parent.parent / "fixtures" / "demo")


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def seed_records() -> dict[str, Any]:
    """The BusinessSnapshot as raw JSON (fresh copy each call, safe to mutate)."""
    return copy.deepcopy(load_fixture("seed.json"))


def demo_incident() -> dict[str, Any]:
    """The NormalizedIncident D-001 (20 of 40 chairs delayed from 21 Oct to 23 Oct)."""
    return copy.deepcopy(load_fixture("incident.json")["expected_normalized_incident"])


def expected_impact() -> dict[str, Any]:
    """The team's expected ImpactResult for the demo (CONTRACTS section 9)."""
    return copy.deepcopy(load_fixture("expected_impact.json"))


def find_record(records: dict[str, Any], collection: str, record_id: str) -> dict[str, Any]:
    for rec in records[collection]:
        if rec.get("id") == record_id:
            return rec
    raise KeyError(f"{collection}/{record_id} not found")


def add_dependency(records: dict[str, Any], dep_id: str, source: tuple[str, str], target: tuple[str, str],
                   dep_type: str, quantity: int | None = None, required_by: str | None = None) -> None:
    records["dependencies"].append({
        "id": dep_id, "source_type": source[0], "source_id": source[1], "target_type": target[0],
        "target_id": target[1], "dependency_type": dep_type, "required_quantity": quantity,
        "required_by": required_by})


# --------------------------------------------------------------------------- #
# Named scenarios:  name -> (snapshot_dict, incident_dict)
# --------------------------------------------------------------------------- #
def _main() -> tuple[dict, dict]:
    return seed_records(), demo_incident()


def _spare_inventory() -> tuple[dict, dict]:
    records, incident = _main()
    find_record(records, "resources", "R-01")["on_hand_quantity"] = 60  # 60 + 20 arriving = 80 >= 70
    return records, incident


def _missing_on_hand() -> tuple[dict, dict]:
    records, incident = _main()
    find_record(records, "resources", "R-01")["on_hand_quantity"] = None
    return records, incident


def _unverified_stock() -> tuple[dict, dict]:
    records, incident = _main()
    find_record(records, "resources", "R-01")["on_hand_verified"] = False
    return records, incident


def _unknown_arrival() -> tuple[dict, dict]:
    records, incident = _main()
    incident["new_arrival_date"] = None
    return records, incident


def _conflicting_data() -> tuple[dict, dict]:
    records, incident = _main()
    add_dependency(records, "DEP-99", ("resource", "R-01"), ("job", "J-02"), "requires", 25, "2026-10-22")  # DEP-04 says 20
    add_dependency(records, "DEP-98", ("resource", "R-01"), ("job", "J-03"), "requires", -5, "2026-10-25")  # invalid
    return records, incident


SCENARIOS: dict[str, Callable[[], tuple[dict, dict]]] = {
    "main": _main,
    "spare_inventory": _spare_inventory,
    "missing_on_hand": _missing_on_hand,
    "unverified_stock": _unverified_stock,
    "unknown_arrival": _unknown_arrival,
    "conflicting_data": _conflicting_data,
}
