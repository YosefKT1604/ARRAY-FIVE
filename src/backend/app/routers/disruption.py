from fastapi import APIRouter, HTTPException

from app.dependencies import DbSession
from app.schemas.disruption import DisruptionCreate, DisruptionCreated, DisruptionOut, DisruptionList
from app.services.disruption import create_disruption, list_disruptions, get_disruption

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