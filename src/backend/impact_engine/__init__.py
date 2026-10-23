"""Impact-analysis engine (Person 3).  Contract entry point:

    analyze_impact(incident: NormalizedIncident, snapshot: BusinessSnapshot) -> ImpactResult
"""
from .analyzer import analyze_impact
from .config import SeverityConfig
from .loader import snapshot_from_raw
from .models import (
    AffectedEntity,
    AnalysisStatus,
    BusinessSnapshot,
    ImpactResult,
    ImpactStatus,
    NormalizedIncident,
)

__all__ = [
    "analyze_impact",
    "snapshot_from_raw",
    "SeverityConfig",
    "BusinessSnapshot",
    "NormalizedIncident",
    "ImpactResult",
    "AffectedEntity",
    "ImpactStatus",
    "AnalysisStatus",
]
