from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.virtual_vehicle import VirtualVehicle
from app.schemas.parcel import ParcelIn
from app.services.data_service import upsert_parcel
from app.services.optimization_service import try_insert

router = APIRouter(prefix="/virtual-vehicles", tags=["virtual-vehicles"])

@router.get("")
def list_virtual_vehicles(db: Session = Depends(get_db)):
    return db.query(VirtualVehicle).order_by(VirtualVehicle.updated_at.desc()).all()

@router.post("/{virtual_vehicle_id}/insert-parcel")
def insert_parcel(virtual_vehicle_id: str, payload: ParcelIn, db: Session = Depends(get_db)):
    vehicle = db.query(VirtualVehicle).filter(
        VirtualVehicle.virtual_vehicle_id == virtual_vehicle_id
    ).first()
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Virtual vehicle not found")

    parcel = upsert_parcel(db, payload)
    inserted, reason = try_insert(db, vehicle, parcel)
    return {
        "virtual_vehicle_id": virtual_vehicle_id,
        "inserted": inserted,
        "reason": reason,
        "remaining_weight_kg": vehicle.capacity_kg - vehicle.used_weight_kg,
        "remaining_volume_m3": vehicle.capacity_m3 - vehicle.used_volume_m3,
    }
