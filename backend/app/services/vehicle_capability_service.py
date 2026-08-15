from sqlalchemy.orm import Session

from app.models.vehicle_capability import VehicleCapability
from app.schemas.vehicle_capability import VehicleCapabilityIn

class DuplicateVehicleCapabilityError(Exception):
    pass

class VehicleCapabilityInUseError(Exception):
    pass

def _check_duplicate_name(db: Session, name: str, exclude_id: int | None = None):
    query = db.query(VehicleCapability).filter(VehicleCapability.name == name)
    if exclude_id is not None:
        query = query.filter(VehicleCapability.id != exclude_id)
    if query.first() is not None:
        raise DuplicateVehicleCapabilityError(f"A vehicle type named '{name}' already exists.")

def create_capability(db: Session, payload: VehicleCapabilityIn) -> VehicleCapability:
    _check_duplicate_name(db, payload.name)
    obj = VehicleCapability(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

def list_capabilities(db: Session, status: str | None = None) -> list[VehicleCapability]:
    query = db.query(VehicleCapability)
    if status is not None:
        query = query.filter(VehicleCapability.status == status)
    return query.order_by(VehicleCapability.name).all()

def get_capability(db: Session, capability_id: int) -> VehicleCapability | None:
    return db.query(VehicleCapability).filter(VehicleCapability.id == capability_id).first()

def update_capability(db: Session, obj: VehicleCapability, payload: VehicleCapabilityIn) -> VehicleCapability:
    _check_duplicate_name(db, payload.name, exclude_id=obj.id)
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj

def delete_capability(db: Session, obj: VehicleCapability) -> None:
    # No Registered Vehicle entity exists yet, so there is nothing to guard against
    # today. Once Registered Vehicles reference a VehicleCapability by id, add a
    # lookup here and raise VehicleCapabilityInUseError instead of deleting.
    db.delete(obj)
    db.commit()

def optimization_ready_capabilities(db: Session) -> list[dict]:
    """Active vehicle-type capability definitions shaped for the NSGA-II optimizer to
    consume as candidate vehicle types (weight/volume ceilings only — availability on a
    given day still depends on Registered Vehicles, which don't exist yet)."""
    capabilities = list_capabilities(db, status="ACTIVE")
    return [
        {
            "id": c.id,
            "name": c.name,
            "max_weight_kg": c.max_weight_kg,
            "max_volume_m3": c.max_volume_m3,
        }
        for c in capabilities
    ]
