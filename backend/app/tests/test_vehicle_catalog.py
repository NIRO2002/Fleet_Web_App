"""Phase 1 gate for the vehicle type catalog: it lives in the database, is
seeded idempotently, and an admin can add/deactivate types through the
service layer with no code change required elsewhere. Phase 6 adds the
stronger invariants (grep for stray literals, empty-catalog error path in
the pipeline, etc.)."""
from app.schemas.vehicle_type import VehicleTypeCatalogIn
from app.services import vehicle_catalog_service as service


def _van_payload(**overrides) -> VehicleTypeCatalogIn:
    data = dict(
        code="VAN",
        display_name="Delivery van",
        capacity_kg=1000.0,
        capacity_m3=8.0,
        cargo_length_cm=280.0,
        cargo_width_cm=170.0,
        cargo_height_cm=170.0,
        max_parcels=120,
        max_stack_layers=4,
        fixed_cost=2500.0,
        cost_per_km=45.0,
        avg_speed_kmh=32.0,
        source="placeholder",
    )
    data.update(overrides)
    return VehicleTypeCatalogIn(**data)


def test_upsert_is_idempotent_by_code(db_session):
    service.upsert_type(db_session, _van_payload())
    service.upsert_type(db_session, _van_payload(capacity_kg=1200.0))

    types = service.list_available_types(db_session, depot_id=None)
    assert len(types) == 1
    assert types[0].capacity_kg == 1200.0


def test_depot_scoping_includes_depot_agnostic_rows(db_session):
    service.upsert_type(db_session, _van_payload(code="VAN", depot_id=None))
    service.upsert_type(db_session, _van_payload(code="LORRY", depot_id="DEPOT-A"))
    service.upsert_type(db_session, _van_payload(code="BIKE", depot_id="DEPOT-B"))

    depot_a_types = {t.code for t in service.list_available_types(db_session, depot_id="DEPOT-A")}
    assert depot_a_types == {"VAN", "LORRY"}


def test_deactivated_type_is_excluded_from_available_list(db_session):
    service.upsert_type(db_session, _van_payload())
    service.deactivate_type(db_session, "VAN")

    types = service.list_available_types(db_session, depot_id=None)
    assert types == []


def test_empty_catalog_returns_empty_list_not_a_default(db_session):
    types = service.list_available_types(db_session, depot_id=None)
    assert types == []


def test_adding_a_type_through_the_service_changes_the_available_set(db_session):
    assert service.list_available_types(db_session, depot_id=None) == []
    service.upsert_type(db_session, _van_payload(code="LORRY"))
    codes = {t.code for t in service.list_available_types(db_session, depot_id=None)}
    assert codes == {"LORRY"}
