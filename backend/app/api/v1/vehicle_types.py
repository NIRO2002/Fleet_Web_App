"""CRUD for the vehicle type catalog (FR03/SO3), so capacities/costs can be
maintained without a deploy. See app/services/vehicle_catalog_service.py."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.vehicle_type import VehicleTypeCatalogIn, VehicleTypeCatalogResponse
from app.services import vehicle_catalog_service as service

router = APIRouter(prefix="/vehicle-types", tags=["vehicle-types"])


@router.get("", response_model=list[VehicleTypeCatalogResponse])
def list_vehicle_types(
    depot_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return service.list_available_types(db, depot_id)


@router.get("/{code}", response_model=VehicleTypeCatalogResponse)
def get_vehicle_type(code: str, db: Session = Depends(get_db)):
    obj = service.get_type(db, code.strip().upper())
    if obj is None:
        raise HTTPException(status_code=404, detail="Vehicle type not found")
    return obj


@router.post("", response_model=VehicleTypeCatalogResponse, status_code=201)
def create_vehicle_type(payload: VehicleTypeCatalogIn, db: Session = Depends(get_db)):
    if service.get_type(db, payload.code) is not None:
        raise HTTPException(status_code=409, detail=f"Vehicle type '{payload.code}' already exists")
    return service.upsert_type(db, payload)


@router.patch("/{code}", response_model=VehicleTypeCatalogResponse)
def update_vehicle_type(code: str, payload: VehicleTypeCatalogIn, db: Session = Depends(get_db)):
    code = code.strip().upper()
    if service.get_type(db, code) is None:
        raise HTTPException(status_code=404, detail="Vehicle type not found")
    if payload.code != code:
        raise HTTPException(status_code=400, detail="Payload code must match path code")
    return service.upsert_type(db, payload)


@router.delete("/{code}", status_code=204)
def deactivate_vehicle_type(code: str, db: Session = Depends(get_db)):
    obj = service.deactivate_type(db, code.strip().upper())
    if obj is None:
        raise HTTPException(status_code=404, detail="Vehicle type not found")
