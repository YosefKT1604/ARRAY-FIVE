import pytest
from fastapi import HTTPException

from app.services.identity import get_current_user
from app.services.permissions import can_decide

def test_owner_can_decide():
    owner = get_current_user("U-01")
    assert can_decide(owner)

def test_staff_cannot_decide():
    staff = get_current_user("U-02")
    assert not can_decide(staff)

def test_unknown_user_is_rejected():
    with pytest.raises(HTTPException):
        get_current_user("U-99")