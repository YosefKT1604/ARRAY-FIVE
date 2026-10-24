import json

from pathlib import Path

from contracts import NormalizedIncident, ImpactResult, BusinessSnapshot, RecoveryPlan

DEMO_DIR = Path(__file__).resolve().parents[4] / "fixtures" / "demo"
DEMO_PLANS = DEMO_DIR / "expected_plans.json"

INCIDENT_FIELDS = ["supplier_id", "resource_id", "delivery_id", "quantity_affected",
                   "original_arrival_date", "new_arrival_date"]
SHORTFALL_FIELDS = ["resource_id", "date", "required", "available", "shortfall"]

def read_demo(name: str) -> dict:
    return json.loads((DEMO_DIR / name).read_text(encoding="utf-8"))

# The fixture plans were written for ONE incident. Showing them for any other would present plans that were
# never checked against it as if they were (CLAUDE.md rule 2), so they are only used when the incident and
# the computed shortfall match the demo exactly. Person 4's real module replaces this check and generate_plans.
def placeholder_applies(incident: NormalizedIncident, impact: ImpactResult) -> bool:
    form = read_demo("incident.json")["form_input"]
    actual = incident.model_dump(mode="json")
    if any(actual[field] != form[field] for field in INCIDENT_FIELDS):
        return False
    expected = [{field: row[field] for field in SHORTFALL_FIELDS} for row in read_demo("expected_impact.json")["resource_shortfalls"]]
    computed = [{field: row[field] for field in SHORTFALL_FIELDS} for row in impact.model_dump(mode="json")["resource_shortfalls"]]
    return computed == expected

# Placeholder until P4's real module is swapped in.
# Argument order follows CONTRACTS §5 (incident, snapshot, impact), so don't reorder it.
def generate_plans(incident: NormalizedIncident, snapshot: BusinessSnapshot, impact: ImpactResult) -> list[RecoveryPlan]:
    data = json.loads(DEMO_PLANS.read_text(encoding="utf-8"))
    return [RecoveryPlan.model_validate({**plan, "disruption_id": incident.id}) for plan in data["plans"]]
