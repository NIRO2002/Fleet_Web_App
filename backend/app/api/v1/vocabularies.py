from fastapi import APIRouter
from app.models.parcel import SERVICE_TYPES
from app.services.clustering_common import PRIORITY_SCORE

router = APIRouter(prefix="/vocabularies", tags=["vocabularies"])

@router.get("/priority-levels")
async def priority_levels(): return PRIORITY_SCORE

@router.get("/service-types")
async def service_types(): return SERVICE_TYPES
