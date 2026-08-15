from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
def login_placeholder():
    return {
        "status": "placeholder",
        "message": "Authentication module belongs to the shared Fleet Web App. Replace this endpoint with your team's implementation."
    }
