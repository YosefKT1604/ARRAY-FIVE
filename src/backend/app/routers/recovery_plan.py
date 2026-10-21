from fastapi import HTTPException, APIRouter
from app.dependencies import DbSession
from contracts import RecoveryPlan
from app.services.recovery_plan import get_recovery_plan, to_contract

router = APIRouter(prefix="/recovery-plans", tags=["Recovery Plans"])
@router.get("/{plan_id}", response_model=RecoveryPlan)
def get_recovery_plan_by_id(plan_id: str, db: DbSession) -> RecoveryPlan:
    record = get_recovery_plan(db, plan_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Recovery plan {plan_id} not found")
    return to_contract(record)
