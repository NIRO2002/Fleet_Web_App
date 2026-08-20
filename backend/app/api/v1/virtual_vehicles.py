from fastapi import APIRouter, HTTPException
from app.models.load_plan import LoadPlan
from app.schemas.parcel import ParcelIn
from app.services.data_service import upsert_parcel
from app.services.optimization_service import try_insert

router = APIRouter(prefix="/virtual-vehicles", tags=["virtual-vehicles"])

@router.get("")
async def list_virtual_vehicles():
    plans = await LoadPlan.find_all().sort("-created_at").to_list()
    return [vehicle for plan in plans for vehicle in plan.vehicles]

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
