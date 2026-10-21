from app.services.identity import CurrentUser
from contracts.enums import Role


def can_decide(user: CurrentUser) -> bool:
    return user.role == Role.OWNER