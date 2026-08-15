from enum import Enum

class Role(str, Enum):
    ADMIN = "admin"
    PLANNER = "planner"
    VIEWER = "viewer"

def require_role(user_role: str, allowed: set[str]) -> bool:
    return user_role in allowed
