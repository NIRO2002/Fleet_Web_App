from fastapi import APIRouter, HTTPException, Query
from app.schemas.vehicle_capability import VehicleCapabilityIn, VehicleCapabilityResponse
from app.services import vehicle_capability_service as service

router = APIRouter(prefix="/vehicle-capabilities", tags=["vehicle-capabilities"])

@router.post("", response_model=VehicleCapabilityResponse, status_code=201)
async def create_vehicle_capability(payload: VehicleCapabilityIn):
    try:
        return await service.create_capability(payload)
    except service.DuplicateVehicleCapabilityError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

@router.get("", response_model=list[VehicleCapabilityResponse])
async def list_vehicle_capabilities(
    status: str | None = Query(default=None, pattern="^(ACTIVE|INACTIVE)$"),
):
    return await service.list_capabilities(status=status)

@router.get("/{capability_id}", response_model=VehicleCapabilityResponse)
async def get_vehicle_capability(capability_id: int):
    obj = await service.get_capability(capability_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Vehicle type not found")
    return obj

@router.put("/{capability_id}", response_model=VehicleCapabilityResponse)
async def update_vehicle_capability(capability_id: int, payload: VehicleCapabilityIn):
    obj = await service.get_capability(capability_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Vehicle type not found")
    try:
        return await service.update_capability(obj, payload)
    except service.DuplicateVehicleCapabilityError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

@router.delete("/{capability_id}", status_code=204)
async def delete_vehicle_capability(capability_id: int):
    obj = await service.get_capability(capability_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Vehicle type not found")
    try:
        await service.delete_capability(obj)
    except service.VehicleCapabilityInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
