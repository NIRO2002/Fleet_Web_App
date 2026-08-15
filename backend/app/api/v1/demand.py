from fastapi import APIRouter

router = APIRouter(prefix="/demand", tags=["demand"])

@router.get("/status")
def status():
    return {
        "status": "placeholder",
        "owner": "shared fleet module",
        "message": "This route is intentionally left for the corresponding fleet application component."
    }
