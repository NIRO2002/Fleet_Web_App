from app.models.vehicle_capability import VehicleCapability
from app.schemas.vehicle_capability import VehicleCapabilityIn
from app.utils_datetime import utcnow

class DuplicateVehicleCapabilityError(Exception): pass
class VehicleCapabilityInUseError(Exception): pass

async def _check_duplicate_name(name, exclude_id=None):
    query = {"name": name}
    if exclude_id is not None:
        query["capability_id"] = {"$ne": exclude_id}
    if await VehicleCapability.find_one(query):
        raise DuplicateVehicleCapabilityError(f"A vehicle type named '{name}' already exists.")

async def create_capability(payload: VehicleCapabilityIn):
    await _check_duplicate_name(payload.name)
    latest = await VehicleCapability.find_all().sort("-capability_id").first_or_none()
    obj = VehicleCapability(capability_id=(latest.capability_id + 1 if latest else 1), **payload.model_dump())
    await obj.insert()
    return obj

async def list_capabilities(status=None):
    query = {"status": status} if status else {}
    return await VehicleCapability.find(query).sort("name").to_list()

async def get_capability(capability_id):
    return await VehicleCapability.find_one(VehicleCapability.capability_id == capability_id)

async def update_capability(obj, payload):
    await _check_duplicate_name(payload.name, obj.capability_id)
    for field, value in payload.model_dump().items(): setattr(obj, field, value)
    obj.updated_at = utcnow()
    await obj.save()
    return obj

async def delete_capability(obj):
    await obj.delete()

async def optimization_ready_capabilities():
    return [{"id": c.id, "name": c.name, "max_weight_kg": c.max_weight_kg, "max_volume_m3": c.max_volume_m3}
            for c in await list_capabilities("ACTIVE")]
