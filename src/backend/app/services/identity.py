import json
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Header
from pydantic import BaseModel

from contracts.enums import Role

SEED_FILE = Path(__file__).resolve().parents[4] / "fixtures" / "demo" / "seed.json"

class CurrentUser(BaseModel):
    id: str
    name: str
    role: Role

def load_demo_users() -> dict[str, CurrentUser]:
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    return {user["id"]: CurrentUser.model_validate(user) for user in data["users"]}

def get_current_user(x_user_id: Annotated[str | None, Header()] = None) -> CurrentUser:
    user = load_demo_users().get(x_user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Missing or unknown X-user-id header")
    return user

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
