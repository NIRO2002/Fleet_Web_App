"""CRUD for the vehicle type catalog (FR03/SO3), so capacities/costs can be
maintained without a deploy. See app/services/vehicle_catalog_service.py."""
from fastapi import APIRouter, HTTPException, Query
from app.schemas.vehicle_type import VehicleTypeCatalogIn, VehicleTypeCatalogResponse
from app.services import vehicle_catalog_service as service

router = APIRouter(prefix="/vehicle-types", tags=["vehicle-types"])


@router.get("", response_model=list[VehicleTypeCatalogResponse])
async def list_vehicle_types(
    depot_id: str | None = Query(default=None),
):
    return await service.list_available_types(depot_id)


@router.get("/{code}", response_model=VehicleTypeCatalogResponse)
async def get_vehicle_type(code: str):
    obj = await service.get_type(code.strip().upper())
    if obj is None:
        raise HTTPException(status_code=404, detail="Vehicle type not found")
    return obj


@router.post("", response_model=VehicleTypeCatalogResponse, status_code=201)
async def create_vehicle_type(payload: VehicleTypeCatalogIn):
    if await service.get_type(payload.code) is not None:
        raise HTTPException(status_code=409, detail=f"Vehicle type '{payload.code}' already exists")
    return await service.upsert_type(payload)


@router.patch("/{code}", response_model=VehicleTypeCatalogResponse)
async def update_vehicle_type(code: str, payload: VehicleTypeCatalogIn):
    code = code.strip().upper()
    if await service.get_type(code) is None:
        raise HTTPException(status_code=404, detail="Vehicle type not found")
    if payload.code != code:
        raise HTTPException(status_code=400, detail="Payload code must match path code")
    return await service.upsert_type(payload)


@router.delete("/{code}", status_code=204)
async def deactivate_vehicle_type(code: str):
    obj = await service.deactivate_type(code.strip().upper())
    if obj is None:
        raise HTTPException(status_code=404, detail="Vehicle type not found")
