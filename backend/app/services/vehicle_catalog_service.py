from app.models.vehicle_type import VehicleTypeCatalog
from app.schemas.vehicle_type import VehicleTypeCatalogIn
from app.utils_datetime import utcnow

class VehicleCatalogCache:
    def __init__(self):
        self._store: dict[str | None, list[VehicleTypeCatalog]] = {}
    async def get_or_load(self, depot_id):
        if depot_id not in self._store:
            self._store[depot_id] = await _query_available_types(depot_id)
        return self._store[depot_id]

async def _query_available_types(depot_id):
    return await VehicleTypeCatalog.find({
        "is_active": True,
        "$or": [{"depot_id": depot_id}, {"depot_id": None}],
    }).sort("code").to_list()

async def _list_available_types(depot_id, delivery_date=None, *, cache=None):
    if cache is not None:
        return await cache.get_or_load(depot_id)
    return await _query_available_types(depot_id)

async def _get_type(code):
    return await VehicleTypeCatalog.find_one(VehicleTypeCatalog.code == code)

async def _upsert_type(payload: VehicleTypeCatalogIn):
    obj = await _get_type(payload.code)
    if obj is None:
        obj = VehicleTypeCatalog(**payload.model_dump())
    else:
        for field, value in payload.model_dump(exclude={"code"}).items():
            setattr(obj, field, value)
        obj.updated_at = utcnow()
    await obj.save()
    return obj

async def _deactivate_type(code):
    obj = await _get_type(code)
    if obj is None:
        return None
    obj.is_active = False
    obj.updated_at = utcnow()
    await obj.save()
    return obj

def _dual(async_fn, args, kwargs):
    if args and hasattr(args[0], "run"):
        return args[0].run(async_fn(*args[1:], **kwargs))
    return async_fn(*args, **kwargs)

def list_available_types(*args, **kwargs): return _dual(_list_available_types, args, kwargs)
def get_type(*args, **kwargs): return _dual(_get_type, args, kwargs)
def upsert_type(*args, **kwargs): return _dual(_upsert_type, args, kwargs)
def deactivate_type(*args, **kwargs): return _dual(_deactivate_type, args, kwargs)
