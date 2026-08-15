from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.vehicle_capability import VehicleCapabilityIn, VehicleCapabilityResponse
from app.services import vehicle_capability_service as service

router = APIRouter(prefix="/vehicle-capabilities", tags=["vehicle-capabilities"])

@router.post("", response_model=VehicleCapabilityResponse, status_code=201)
def create_vehicle_capability(payload: VehicleCapabilityIn, db: Session = Depends(get_db)):
    try:
        return service.create_capability(db, payload)
    except service.DuplicateVehicleCapabilityError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

@router.get("", response_model=list[VehicleCapabilityResponse])
def list_vehicle_capabilities(
    status: str | None = Query(default=None, pattern="^(ACTIVE|INACTIVE)$"),
    db: Session = Depends(get_db),
):
    return service.list_capabilities(db, status=status)

@router.get("/{capability_id}", response_model=VehicleCapabilityResponse)
def get_vehicle_capability(capability_id: int, db: Session = Depends(get_db)):
    obj = service.get_capability(db, capability_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Vehicle type not found")
    return obj

@router.put("/{capability_id}", response_model=VehicleCapabilityResponse)
def update_vehicle_capability(capability_id: int, payload: VehicleCapabilityIn, db: Session = Depends(get_db)):
    obj = service.get_capability(db, capability_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Vehicle type not found")
    try:
        return service.update_capability(db, obj, payload)
    except service.DuplicateVehicleCapabilityError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

@router.delete("/{capability_id}", status_code=204)
def delete_vehicle_capability(capability_id: int, db: Session = Depends(get_db)):
    obj = service.get_capability(db, capability_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Vehicle type not found")
    try:
        service.delete_capability(db, obj)
    except service.VehicleCapabilityInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
