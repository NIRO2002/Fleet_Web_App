from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db

def get_current_user():
    # Placeholder for the friend's/auth team's implementation.
    return {"user_id": "dev-user", "role": "admin"}

def require_planner_or_admin(user=Depends(get_current_user)):
    if user["role"] not in {"admin", "planner"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Planner role required")
    return user
