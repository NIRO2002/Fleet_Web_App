"""`vehicle_type_catalog` is the single source of truth for vehicle specs
(see docs/DESIGN_DECISIONS.md and app/services/vehicle_catalog_service.py):
the Vehicle Types CRUD page and NSGA-II must both read/write it, and no
other vehicle-type store may exist. These tests prove the service layer's
CRUD persists correctly and, critically, that `assignment_problem`'s
`load_catalog_snapshot` -- the only way NSGA-II obtains vehicle data -- is a
live read-through of the catalog, not a cached or hardcoded value.

Tests use a plain-object fake in place of the real `VehicleTypeCatalog`
Beanie Document (constructing a real Document requires `init_beanie`
against a live Mongo connection, which this repo's test suite never does --
see test_depot_constraints.py for the same monkeypatch-only convention)."""
import asyncio

from app.db.seed_vehicle_types import FIELD_DATA_VEHICLE_TYPES
from app.schemas.vehicle_type import VehicleTypeCatalogIn
from app.services import vehicle_catalog_service as service


class FakeVehicleTypeCatalog:
    """Stands in for the real Beanie Document: same attribute surface,
    no DB connection required to construct or `save()`."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    async def save(self):
        return self


def _payload(code="TEST_TYPE", **overrides) -> VehicleTypeCatalogIn:
    base = dict(
        code=code,
        display_name="Test Vehicle",
        category="Test",
        capacity_kg=100.0,
        capacity_m3=1.0,
        cargo_length_cm=100.0,
        cargo_width_cm=100.0,
        cargo_height_cm=100.0,
        max_parcels=10,
        max_stack_layers=1,
        fixed_cost=100.0,
        cost_per_km=10.0,
        avg_speed_kmh=30.0,
        has_tail_lift=False,
        available_from="06:00",
        available_until="20:00",
    )
    base.update(overrides)
    return VehicleTypeCatalogIn(**base)


def test_upsert_type_creates_and_updates(monkeypatch):
    """A second `upsert_type` call for the same code updates the existing
    row in place -- never a duplicate."""
    store: dict[str, FakeVehicleTypeCatalog] = {}

    async def fake_get_type(code):
        return store.get(code)

    monkeypatch.setattr(service, "_get_type", fake_get_type)
    monkeypatch.setattr(service, "VehicleTypeCatalog", FakeVehicleTypeCatalog)

    created = asyncio.run(service.upsert_type(_payload(capacity_kg=100.0)))
    store[created.code] = created
    assert created.capacity_kg == 100.0

    updated = asyncio.run(service.upsert_type(_payload(capacity_kg=250.0)))
    store[updated.code] = updated
    assert updated.capacity_kg == 250.0
    assert len(store) == 1
    assert updated is created  # same row mutated in place, not a new one


def test_deactivate_excludes_from_list_available_types(monkeypatch):
    active = FakeVehicleTypeCatalog(**_payload(code="ACTIVE_TYPE").model_dump())
    other = FakeVehicleTypeCatalog(**_payload(code="OTHER_TYPE").model_dump())
    store = {"ACTIVE_TYPE": active, "OTHER_TYPE": other}

    async def fake_get_type(code):
        return store.get(code)

    async def fake_query_available_types(depot_id):
        return [v for v in store.values() if v.is_active and v.depot_id in (depot_id, None)]

    monkeypatch.setattr(service, "_get_type", fake_get_type)
    monkeypatch.setattr(service, "_query_available_types", fake_query_available_types)

    codes_before = {v.code for v in asyncio.run(service.list_available_types(None))}
    assert codes_before == {"ACTIVE_TYPE", "OTHER_TYPE"}

    asyncio.run(service.deactivate_type("ACTIVE_TYPE"))

    codes_after = {v.code for v in asyncio.run(service.list_available_types(None))}
    assert codes_after == {"OTHER_TYPE"}


def test_optimizer_reflects_updated_catalog_value(monkeypatch):
    """The core consolidation proof: NSGA-II's `load_catalog_snapshot` must
    see a catalog edit immediately, with no stale/cached/hardcoded value in
    between -- this is the seam the whole optimizer reads through."""
    from app.optimization import assignment_problem

    row = FakeVehicleTypeCatalog(**_payload(code="LIVE_TYPE", capacity_kg=500.0).model_dump())

    async def fake_query_available_types(depot_id):
        return [row]

    monkeypatch.setattr(service, "_query_available_types", fake_query_available_types)

    snapshot = asyncio.run(assignment_problem.load_catalog_snapshot(None))
    assert snapshot[0].code == "LIVE_TYPE"
    assert snapshot[0].capacity_kg == 500.0

    row.capacity_kg = 999.0  # simulates an edit persisted via the API/service layer

    snapshot_after_edit = asyncio.run(assignment_problem.load_catalog_snapshot(None))
    assert snapshot_after_edit[0].capacity_kg == 999.0


def test_seed_vehicle_types_unchanged_and_categorized():
    """Adding `category` must not silently alter the field-data seed
    values NSGA-II has always used."""
    by_code = {v.code: v for v in FIELD_DATA_VEHICLE_TYPES}
    assert len(by_code) == 7
    for v in FIELD_DATA_VEHICLE_TYPES:
        assert v.category, f"{v.code} missing category"

    assert by_code["BIKE"].capacity_kg == 25.0
    assert by_code["APE_CARGO"].capacity_kg == 496.0
    assert by_code["TVS_KING"].capacity_kg == 450.0
    assert by_code["MICRO_VAN"].capacity_kg == 350.0
    assert by_code["VAN_MED"].capacity_kg == 1100.0
    assert by_code["TRUCK_2T"].capacity_kg == 2500.0
    assert by_code["TRUCK_4T"].capacity_kg == 4500.0
