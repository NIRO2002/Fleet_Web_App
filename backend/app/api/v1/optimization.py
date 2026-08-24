from datetime import date as date_type

from fastapi import APIRouter, HTTPException, Response

from app.core.config import settings
from app.models.load_plan import LoadPlan
from app.models.parcel import Parcel
from app.schemas.optimization import OptimizationRequest
from app.services.optimization_service import optimize_load
from app.services.depot_service import get_depot_or_fail
from app.optimization.assignment_problem import AssignmentConfig
from app.services.export_service import load_plan_csv, load_plan_payload

router = APIRouter(prefix="/optimization", tags=["optimization"])


@router.get("/plans")
async def find_plan(depot_id: str, delivery_date: date_type):
    """Most recent plan for a (depot_id, delivery_date), if one exists --
    lets a caller avoid re-running an optimization that already ran."""
    plan = await LoadPlan.find(
        LoadPlan.depot_id == depot_id, LoadPlan.delivery_date == delivery_date,
    ).sort("-created_at").first_or_none()
    if plan is None:
        return None
    return await load_plan_payload(plan.plan_id)


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
            # -1 marks HDBSCAN noise that handle_noise
            # (app/services/clustering_common.py) could not reassign to a
            # nearby real cluster within noise_max_assign_km -- these
            # parcels are genuinely persisted with cluster_id=-1, not a
            # value that "should never" occur. It's still not a valid
            # optimization target: -1 isn't a real spatial cluster, so
            # there's no coherent route to build a vehicle around. See
            # GET /parcels/clustering/unassigned to inspect them instead.
            raise HTTPException(status_code=400, detail="cluster_id -1 (noise) is not a valid optimization target")
        # Scoped to one (depot_id, delivery_date) planning instance -- HDBSCAN
        # labels restart at 0 per instance (see
        # app/services/clustering_service.py), so the same cluster_id exists
        # across many instances. OptimizationRequest's validator guarantees
        # depot_id/delivery_date are present whenever cluster_id is.
        parcels = await Parcel.find({
            "cluster_id": payload.cluster_id,
            "depot_id": payload.depot_id,
            "delivery_date": payload.delivery_date,
        }).to_list()
    else:
        raise HTTPException(status_code=400, detail="Provide cluster_id or parcel_ids")

    if not parcels:
        raise HTTPException(status_code=404, detail="No matching parcels")

    # The cluster_id branch's query above already guarantees a single
    # depot_id/delivery_date by construction, so these are now unreachable
    # for that branch. The parcel_ids branch is NOT scoped by that query --
    # an arbitrary parcel_ids list can still span depots/dates -- so these
    # remain real (if now assertion-style) checks, not dead code.
    depot_ids = {p.depot_id for p in parcels}
    assert len(depot_ids) == 1 and None not in depot_ids, "Selected parcels must share exactly one depot_id"
    delivery_dates = {p.delivery_date for p in parcels}
    assert len(delivery_dates) == 1, "Selected parcels must share exactly one delivery_date"

    resolved_depot_id = next(iter(depot_ids))

    try:
        depot = await get_depot_or_fail(resolved_depot_id)
        if (payload.depot_latitude is None) != (payload.depot_longitude is None):
            raise ValueError("depot_latitude and depot_longitude overrides must be supplied together")
        # A depot_latitude/depot_longitude override is only ever meaningful
        # for the depot the resolved parcels actually belong to. The
        # cluster_id branch's query makes payload.depot_id == resolved_depot_id
        # unreachable-mismatch by construction; this guards the parcel_ids
        # branch, where a caller-supplied depot_id is only a hint and can
        # legitimately disagree with the parcels actually resolved.
        if (
            payload.depot_latitude is not None
            and payload.depot_id is not None
            and payload.depot_id != resolved_depot_id
        ):
            raise ValueError(
                f"depot_latitude/depot_longitude override does not match the resolved parcels' depot_id "
                f"(requested depot_id={payload.depot_id!r}, resolved depot_id={resolved_depot_id!r})"
            )
        depot_lat = payload.depot_latitude if payload.depot_latitude is not None else depot.lat
        depot_lon = payload.depot_longitude if payload.depot_longitude is not None else depot.lng
        result, _ = await optimize_load(
            parcels,
            depot_id=resolved_depot_id,
            depot_lat=depot_lat,
            depot_lon=depot_lon,
            delivery_date=next(iter(delivery_dates)),
            config=AssignmentConfig(
                depot_lat=depot_lat,
                depot_lon=depot_lon,
                max_vehicle_slots=depot.vehicle_capacity,
            ),
            depot_operating_end=depot.operating_hours_end,
            depot_vehicle_capacity=depot.vehicle_capacity,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
