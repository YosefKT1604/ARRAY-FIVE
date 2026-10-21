from fastapi import APIRouter, HTTPException

from sqlalchemy.orm import Session
from app.dependencies import DbSession
from app.models.disruption import Disruption
from app.schemas.disruption import DisruptionCreate, DisruptionCreated, DisruptionOut, DisruptionList
from app.services.disruption import create_disruption, list_disruptions, get_disruption, analyze_disruption
from contracts import DisruptionStatus, ImpactResult

router = APIRouter(prefix="/disruptions", tags=["Disruptions"])

@router.post("", status_code=201, response_model=DisruptionCreated)
def report_disruption(data: DisruptionCreate, db: DbSession) -> DisruptionCreated:
    disruption = create_disruption(db, data)
    return DisruptionCreated(disruption=disruption, incident=disruption.incident)

@router.get("", response_model=DisruptionList)
def get_disruptions(db: DbSession) -> DisruptionList:
    return DisruptionList(items=list_disruptions(db))

@router.get("/{disruption_id}", response_model=DisruptionOut)
def get_disruption_by_id(db: DbSession, disruption_id: str) -> DisruptionOut:
    disruption = get_disruption(db, disruption_id)
    if disruption is None:
        raise HTTPException(status_code=404, detail="Disruption not found")
    return DisruptionOut.model_validate(disruption)

def get_disruption_or_404(db: Session, disruption_id: str) -> Disruption:
    disruption = get_disruption(db, disruption_id)
    if disruption is None:
        raise HTTPException(status_code=404, detail=f"Disruption {disruption_id} not found")
    return disruption

@router.post("/{disruption_id}/analyze", response_model=ImpactResult)
def analyze(db: DbSession, disruption_id: str) -> ImpactResult:
    disruption = get_disruption_or_404(db, disruption_id)
    if disruption.status == DisruptionStatus.NEEDS_CLARIFICATION:
        raise HTTPException(status_code=409, detail="Disruption needs clarification before it can be analyzed")
    return analyze_disruption(db, disruption)

@router.get("/{disruption_id}/impact", response_model=ImpactResult)
def get_impact(disruption_id: str, db: DbSession) -> ImpactResult:
    disruption = get_disruption_or_404(db, disruption_id)
    if disruption.impact is None:
        raise HTTPException(status_code=404, detail=f"Disruption {disruption_id} has not been analyzed yet")
    return ImpactResult.model_validate(disruption.impact)
