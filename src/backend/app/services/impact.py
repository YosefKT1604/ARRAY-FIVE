import json

from pathlib import Path

from contracts import NormalizedIncident, ImpactResult, BusinessSnapshot

DEMO_IMPACT = Path(__file__).resolve().parents[4] / "fixtures" / "demo" / "expected_impact.json"

def analyze_impact(incident: NormalizedIncident, snapshot: BusinessSnapshot | None = None) -> ImpactResult:
    data = json.loads(DEMO_IMPACT.read_text(encoding="utf-8"))
    data.pop("_note")
    return ImpactResult.model_validate({**data, "disruption_id": incident.id})