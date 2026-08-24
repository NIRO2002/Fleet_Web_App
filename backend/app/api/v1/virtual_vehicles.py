from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.models.load_plan import LoadPlan
from app.schemas.parcel import ParcelIn
from app.services.data_service import upsert_parcel
from app.services.optimization_service import try_insert
from app.utils_datetime import utcnow

router = APIRouter(prefix="/virtual-vehicles", tags=["virtual-vehicles"])

# Supervisor-demo lifecycle: the only transition a human ever triggers is
# marking a loaded vehicle READY for the fleet optimizer to collect.
_ALLOWED_TRANSITIONS = {("LOADING", "READY")}

class StatusUpdate(BaseModel):
    status: str

@router.get("")
async def list_virtual_vehicles(plan_id: str | None = Query(default=None), vehicle_type: str | None = Query(default=None), status: str | None = Query(default=None)):
    plans = await LoadPlan.find({"plan_id": plan_id} if plan_id else {}).sort("-created_at").to_list()
    rows = []
    for plan in plans:
        for vehicle in plan.vehicles:
            if vehicle_type and vehicle.vehicle_type_code != vehicle_type: continue
            if status and vehicle.status != status: continue
            rows.append({**vehicle.model_dump(), "plan_id": plan.plan_id})
    return rows

@router.patch("/{virtual_vehicle_id}/status")
async def update_status(virtual_vehicle_id: str, payload: StatusUpdate):
    plan = await LoadPlan.find_one({"vehicles.virtual_vehicle_id": virtual_vehicle_id})
    vehicle = next((v for v in plan.vehicles if v.virtual_vehicle_id == virtual_vehicle_id), None) if plan else None
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Virtual vehicle not found")

    transition = (vehicle.status, payload.status)
    if transition not in _ALLOWED_TRANSITIONS:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition virtual vehicle from {vehicle.status} to {payload.status}",
        )

    vehicle.status = payload.status
    vehicle.ready_at = utcnow()
    vehicle.updated_at = utcnow()
    await plan.save()
    return vehicle

@router.post("/{virtual_vehicle_id}/insert-parcel")
async def insert_parcel(virtual_vehicle_id: str, payload: ParcelIn):
    plan = await LoadPlan.find_one({"vehicles.virtual_vehicle_id": virtual_vehicle_id})
    vehicle = next((v for v in plan.vehicles if v.virtual_vehicle_id == virtual_vehicle_id), None) if plan else None
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Virtual vehicle not found")

    parcel = await upsert_parcel(payload)
    inserted, reason = await try_insert(plan, vehicle, parcel)
    return {
        "virtual_vehicle_id": virtual_vehicle_id,
        "inserted": inserted,
        "reason": reason,
        "remaining_weight_kg": vehicle.capacity_kg - vehicle.used_weight_kg,
        "remaining_volume_m3": vehicle.capacity_m3 - vehicle.used_volume_m3,
    }
