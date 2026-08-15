from fastapi import APIRouter

router = APIRouter(prefix="/routes", tags=["routes"])

@router.get("/status")
def status():
    return {
        "status": "placeholder",
        "owner": "shared fleet module",
        "message": "This route is intentionally left for the corresponding fleet application component."
    }
