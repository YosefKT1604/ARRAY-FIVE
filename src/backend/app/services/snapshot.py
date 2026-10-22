import json
from datetime import datetime, UTC
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

import contracts
from app.db.database import Base
from app.models.commitment import Commitment
from app.models.delivery import Delivery
from app.models.dependency import Dependency
from app.models.job import Job
from app.models.resource import Resource
from app.models.supplier import Supplier, SupplierOffering
from contracts import BusinessSnapshot, NormalizedIncident

SEED_FILE = Path(__file__).resolve().parents[4] / "fixtures" / "demo" / "seed.json"

def load_business() -> contracts.Business:
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    return contracts.Business.model_validate(data["business"])

def to_contracts(db: Session, model: type[Base], contract: type[contracts.ContractModel]) -> list:
    return [contract.model_validate(row) for row in db.scalars(select(model).order_by(model.id))]

def build_snapshot(db: Session, incident: NormalizedIncident) -> BusinessSnapshot:
    return BusinessSnapshot(as_of=datetime.now(UTC),
        business=load_business(),
        suppliers=to_contracts(db, Supplier, contracts.Supplier),
        supplier_offerings=to_contracts(db, SupplierOffering, contracts.SupplierOffering),
        resources=to_contracts(db, Resource, contracts.Resource),
        deliveries=to_contracts(db, Delivery, contracts.Delivery),
        jobs=to_contracts(db, Job, contracts.Job),
        commitments=to_contracts(db, Commitment, contracts.Commitment),
        dependencies=to_contracts(db, Dependency, contracts.Dependency),
    )

