from contracts import NormalizedIncident, ImpactResult, BusinessSnapshot
from impact_engine import analyze_impact as run_impact_engine

# P3's engine (impact_engine/) reads plain JSON-style data and returns its own, richer ImpactResult.
# to_contract() keeps only the contract fields; the two extensions the contract allows are added back,
# so a "partial" or "failed" run is never mistaken for a clean one.
# Keep the signature exactly as CONTRACTS §5 so callers don't change.
def analyze_impact(incident: NormalizedIncident, snapshot: BusinessSnapshot) -> ImpactResult:
    result = run_impact_engine(incident.model_dump(mode="json"), snapshot.model_dump(mode="json"))
    data = result.to_contract()
    data["analysis_status"] = result.analysis_status.value
    data["data_issues"] = [issue.model_dump(mode="json") for issue in result.data_issues]
    return ImpactResult.model_validate(data)
