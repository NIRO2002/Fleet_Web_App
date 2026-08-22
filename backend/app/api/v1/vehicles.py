from datetime import date as date_type

from fastapi import APIRouter, Query

from app.models.load_plan import LoadPlan
from app.models.parcel import Parcel
from app.models.vehicle_type import VehicleTypeCatalog

router = APIRouter(prefix="/vehicles", tags=["vehicles"])

@router.get("/status")
def status():
    return {
        "status": "placeholder",
        "owner": "shared fleet module",
        "message": "This route is intentionally left for the corresponding fleet application component."
    }

@router.get("/ready")
async def list_ready_vehicles(depot_id: str | None = None, delivery_date: date_type | None = None):
    """The fleet-optimizer handoff. Every READY virtual vehicle, with its
    delivery stops, for the downstream route optimizer to pick up.
    `deliverySequence` is this module's nearest-neighbour estimate, not an
    optimized route -- reordering stops is the downstream module's job."""
    query: dict = {"vehicles.status": "READY"}
    if depot_id is not None:
        query["depot_id"] = depot_id
    if delivery_date is not None:
        query["delivery_date"] = delivery_date
    plans = await LoadPlan.find(query).to_list()

    display_names = {v.code: v.display_name async for v in VehicleTypeCatalog.find_all()}

    ready = []
    for plan in plans:
        for vehicle in plan.vehicles:
            if vehicle.status != "READY":
                continue
            parcel_ids = [a.parcel_id for a in vehicle.assignments]
            parcels = {p.parcel_id: p for p in await Parcel.find({"parcel_id": {"$in": parcel_ids}}).to_list()}
            stops = [
                {
                    "parcelId": a.parcel_id,
                    "lat": parcels[a.parcel_id].latitude,
                    "lng": parcels[a.parcel_id].longitude,
                    "deliverySequence": a.delivery_sequence,
                    "timeWindowStart": parcels[a.parcel_id].time_window_start,
                    "timeWindowEnd": parcels[a.parcel_id].time_window_end,
                }
                for a in sorted(vehicle.assignments, key=lambda a: a.delivery_sequence)
                if a.parcel_id in parcels
            ]
            ready.append({
                "vehicleId": vehicle.virtual_vehicle_id,
                "vehicleType": vehicle.vehicle_type_code,
                "vehicleTypeName": display_names.get(vehicle.vehicle_type_code, vehicle.vehicle_type_code),
                "status": vehicle.status,
                "loadPlanId": plan.plan_id,
                "depotId": plan.depot_id,
                "deliveryDate": plan.delivery_date.isoformat(),
                "parcelCount": vehicle.parcel_count,
                "utilization": vehicle.utilization,
                "totalWeightKg": vehicle.used_weight_kg,
                "totalVolumeM3": vehicle.used_volume_m3,
                "readyAt": vehicle.ready_at.isoformat() if vehicle.ready_at else None,
                "stops": stops,
            })
    return ready
