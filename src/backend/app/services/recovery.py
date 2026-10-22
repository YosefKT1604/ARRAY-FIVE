import json

from pathlib import Path

from contracts import NormalizedIncident, ImpactResult, BusinessSnapshot, RecoveryPlan

DEMO_PLANS = Path(__file__).resolve().parents[4] / "fixtures" / "demo" / "expected_plans.json"

# Placeholder until P4's real module is swapped in.
# Argument order follows CONTRACTS §5 (incident, snapshot, impact), so don't reorder it.
def generate_plans(incident: NormalizedIncident, snapshot: BusinessSnapshot, impact: ImpactResult) -> list[RecoveryPlan]:
    data = json.loads(DEMO_PLANS.read_text(encoding="utf-8"))
    return [RecoveryPlan.model_validate({**plan, "disruption_id": incident.id}) for plan in data["plans"]]
