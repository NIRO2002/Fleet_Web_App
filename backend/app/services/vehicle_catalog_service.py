"""Vehicle type catalog access.

Satisfies FR03/SO3. This is the *only* code path allowed to hand vehicle
capacity/cost data to the optimizer (Phase 3) — `app/services/` and
`app/optimization/` must never contain a vehicle capacity literal. Callers
that need to guarantee a single database round trip for the lifetime of one
optimization run should build a `VehicleCatalogCache` once and pass it
through, rather than relying on any implicit global cache (a module-level
cache would leak state across independent DB sessions, which is unsafe for
tests and for concurrent requests).
"""
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.vehicle_type import VehicleTypeCatalog
from app.schemas.vehicle_type import VehicleTypeCatalogIn


class VehicleCatalogCache:
    """Per-run cache: a single optimization pipeline run should hit
    `vehicle_type_catalog` once, not once per GA evaluation. Create one
    instance per `run_load_planning` call and thread it through."""

    def __init__(self) -> None:
        self._store: dict[str | None, list[VehicleTypeCatalog]] = {}

    def get_or_load(self, db: Session, depot_id: str | None) -> list[VehicleTypeCatalog]:
        if depot_id not in self._store:
            self._store[depot_id] = _query_available_types(db, depot_id)
        return self._store[depot_id]


def _query_available_types(db: Session, depot_id: str | None) -> list[VehicleTypeCatalog]:
    return (
        db.query(VehicleTypeCatalog)
        .filter(
            VehicleTypeCatalog.is_active.is_(True),
            or_(
                VehicleTypeCatalog.depot_id == depot_id,
                VehicleTypeCatalog.depot_id.is_(None),
            ),
        )
        .order_by(VehicleTypeCatalog.code)
        .all()
    )


def list_available_types(
    db: Session,
    depot_id: str | None,
    delivery_date=None,  # noqa: ARG001 - reserved for future date-scoped availability
    *,
    cache: VehicleCatalogCache | None = None,
) -> list[VehicleTypeCatalog]:
    """Active vehicle types usable at `depot_id` (depot-specific rows plus
    depot-agnostic rows where `depot_id IS NULL`). This must never fall back
    to a built-in default — an empty result is a caller error to surface,
    not to paper over."""
    if cache is not None:
        return cache.get_or_load(db, depot_id)
    return _query_available_types(db, depot_id)


def get_type(db: Session, code: str) -> VehicleTypeCatalog | None:
    return db.query(VehicleTypeCatalog).filter(VehicleTypeCatalog.code == code).first()


def upsert_type(db: Session, payload: VehicleTypeCatalogIn) -> VehicleTypeCatalog:
    obj = get_type(db, payload.code)
    if obj is None:
        obj = VehicleTypeCatalog(code=payload.code)
        db.add(obj)
    for field, value in payload.model_dump(exclude={"code"}).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


def deactivate_type(db: Session, code: str) -> VehicleTypeCatalog | None:
    obj = get_type(db, code)
    if obj is None:
        return None
    obj.is_active = False
    db.commit()
    db.refresh(obj)
    return obj
