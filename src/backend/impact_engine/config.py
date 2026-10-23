"""Configurable severity weights and thresholds.

These numbers are *judgement calls*, not facts discovered from data. Change them
to match the business owner's priorities; the values used are echoed back in
every ImpactResult so a score can always be reproduced.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


def _default_importance() -> dict[str, float]:
    # Contract Priority enum (low | medium | high | critical) -> 0..1
    return {"low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0}


class SeverityConfig(BaseModel):
    # Weights (relative; normalised, so they need not sum to 1).
    weight_deadline_urgency: float = Field(0.4, ge=0)
    weight_resource_shortfall: float = Field(0.4, ge=0)
    weight_commitment_importance: float = Field(0.2, ge=0)

    # Urgency is 1.0 when the resource is needed today (or overdue), falling
    # linearly to 0.0 when it is needed this many days or more ahead.
    urgency_horizon_days: int = Field(14, gt=0)

    # Job.priority -> importance factor (0..1).
    priority_importance: dict[str, float] = Field(default_factory=_default_importance)

    # Placeholder used ONLY when a factor cannot be measured. Any score that
    # used it lists the factor in `assumed_factors`.
    unknown_factor_default: float = Field(0.5, ge=0, le=1)

    # Score is 0..10. Priority bands for the *score*:
    threshold_critical: float = 7.5
    threshold_high: float = 5.0
    threshold_medium: float = 2.5

    # Safety cap on enumerated dependency paths per entity.
    max_paths_per_entity: int = Field(20, gt=0)

    @model_validator(mode="after")
    def _check_consistency(self) -> "SeverityConfig":
        total = (
            self.weight_deadline_urgency
            + self.weight_resource_shortfall
            + self.weight_commitment_importance
        )
        if total <= 0:
            raise ValueError("At least one severity weight must be greater than zero.")
        if not (self.threshold_medium <= self.threshold_high <= self.threshold_critical):
            raise ValueError("Thresholds must satisfy medium <= high <= critical.")
        if any(not 0 <= v <= 1 for v in self.priority_importance.values()):
            raise ValueError("priority_importance values must be between 0 and 1.")
        return self
