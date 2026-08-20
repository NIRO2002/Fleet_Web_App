from fastapi import APIRouter, HTTPException, Response

from app.core.config import settings
from app.models.parcel import Parcel
from app.schemas.optimization import OptimizationRequest
from app.services.optimization_service import optimize_load
from app.services.export_service import load_plan_csv, load_plan_payload

router = APIRouter(prefix="/optimization", tags=["optimization"])


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str):
    return await load_plan_payload(plan_id)


@router.get("/plans/{plan_id}/export.csv")
async def export_plan_csv(plan_id: str):
    return Response(
        await load_plan_csv(plan_id),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{plan_id}.csv"'},
    )

@router.post("/run")
async def run(payload: OptimizationRequest):
    if payload.parcel_ids:
        parcels = await Parcel.find({"parcel_id": {"$in": payload.parcel_ids}}).to_list()
    elif payload.cluster_id is not None:
        if payload.cluster_id == -1:
            # HDBSCAN noise is reassigned by Phase 2's handle_noise before
            # persistence, so a stored cluster_id of -1 should never be a
            # real, optimizable cluster.
            raise HTTPException(status_code=400, detail="cluster_id -1 (noise) is not a valid optimization target")
        parcels = await Parcel.find(Parcel.cluster_id == payload.cluster_id).to_list()
    else:
        raise HTTPException(status_code=400, detail="Provide cluster_id or parcel_ids")

    if not parcels:
        raise HTTPException(status_code=404, detail="No matching parcels")

    depot_ids = {p.depot_id for p in parcels}
    if len(depot_ids) != 1 or None in depot_ids:
        raise HTTPException(status_code=400, detail="Selected parcels must share exactly one depot_id")
    delivery_dates = {p.delivery_date for p in parcels}
    if len(delivery_dates) != 1:
        raise HTTPException(status_code=400, detail="Selected parcels must share exactly one delivery_date")

    try:
        depot_lat = payload.depot_latitude or settings.depot_latitude
        depot_lon = payload.depot_longitude or settings.depot_longitude
        result, _ = await optimize_load(
            parcels,
            depot_id=next(iter(depot_ids)),
            depot_lat=depot_lat,
            depot_lon=depot_lon,
            delivery_date=next(iter(delivery_dates)),
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
