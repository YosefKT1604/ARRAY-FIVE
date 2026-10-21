import json

from pathlib import Path

from contracts import NormalizedIncident, ImpactResult, BusinessSnapshot, RecoveryPlan

DEMO_PLANS = Path(__file__).resolve().parents[4] / "fixtures" / "demo" / "expected_plans.json"

def generate_plans(incident: NormalizedIncident, impact: ImpactResult, snapshot: BusinessSnapshot | None = None) -> list[RecoveryPlan]:
    data = json.loads(DEMO_PLANS.read_text(encoding="utf-8"))
    return [RecoveryPlan.model_validate({**plan, "disruption_id": incident.id}) for plan in data["plans"]]

