from fastapi import APIRouter
from app.models.depot import Depot

router = APIRouter(prefix="/depots", tags=["depots"])

@router.get("")
async def list_depots():
    rows = await Depot.find_all().sort("depot_id").to_list()
    return [{"depot_id": r.depot_id, "depot_name": r.depot_name, "lat": r.lat, "lng": r.lng} for r in rows]
