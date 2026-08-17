"""Phase 1 gate for the vehicle type catalog: it lives in the database, is
seeded idempotently, and an admin can add/deactivate types through the
service layer with no code change required elsewhere. Phase 6 adds the
stronger invariants (grep for stray literals, empty-catalog error path in
the pipeline, etc.).

Fix Pass 2 item A.7 adds: the real 10-row catalog seeds correctly (T == 10),
adding an 11th row changes `AssignmentProblem.T` with no code change, and a
dimensional-fit verification against a synthetic parcel set (the real
`parcels_table1_sample_5000.csv` referenced by the spec doesn't exist on
this machine -- see docs/DESIGN_DECISIONS.md and
app/evaluation/synthetic_data.py -- so this reports whatever fit-rates the
synthetic data actually produces rather than asserting the doc's figures)."""
from types import SimpleNamespace

from app.db.seed_vehicle_types import VEHICLE_TYPES
from app.evaluation.synthetic_data import generate_synthetic_parcels
from app.optimization.assignment_problem import (
    AssignmentConfig,
    AssignmentProblem,
    _dimension_fits,
    load_catalog_snapshot,
)
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


def _seed_real_catalog(db_session):
    for payload in VEHICLE_TYPES:
        service.upsert_type(db_session, payload)


def test_real_catalog_seeds_ten_types(db_session):
    """A.7: T == 10 (7 field-data rows + 3 estimated reefer variants)."""
    _seed_real_catalog(db_session)
    types = service.list_available_types(db_session, depot_id=None)
    assert len(types) == 10
    assert {t.code for t in types} == {
        "BIKE", "APE_CARGO", "TVS_KING", "MICRO_VAN", "VAN_MED", "TRUCK_2T", "TRUCK_4T",
        "VAN_MED_REEFER", "TRUCK_2T_REEFER", "TRUCK_4T_REEFER",
    }
    assert {t.code for t in types if t.source == "field_data"} == {
        "BIKE", "APE_CARGO", "TVS_KING", "MICRO_VAN", "VAN_MED", "TRUCK_2T", "TRUCK_4T",
    }
    assert {t.code for t in types if t.source == "estimated_variant"} == {
        "VAN_MED_REEFER", "TRUCK_2T_REEFER", "TRUCK_4T_REEFER",
    }


def test_assignment_problem_search_space_grows_with_an_eleventh_catalog_row(db_session):
    """Phase 3.1 requirement, exercised for real: T changes with the
    catalog, no code change, going from 10 rows to 11."""
    _seed_real_catalog(db_session)
    catalog_10 = load_catalog_snapshot(db_session, depot_id=None)
    assert len(catalog_10) == 10

    service.upsert_type(db_session, _van_payload(code="EXTRA_VAN"))
    catalog_11 = load_catalog_snapshot(db_session, depot_id=None)
    assert len(catalog_11) == 11

    parcels = [
        SimpleNamespace(latitude=6.9271, longitude=79.8612, weight_kg=5.0, volume_m3=0.02,
                        time_window_start="09:00", time_window_end="17:00", two_person_lift=False)
        for _ in range(5)
    ]
    config = AssignmentConfig(depot_lat=6.9271, depot_lon=79.8612)
    problem_10 = AssignmentProblem(parcels, catalog_10, config)
    problem_11 = AssignmentProblem(parcels, catalog_11, config)
    assert problem_10.T == 10
    assert problem_11.T == 11


def test_bike_dimensional_fit_rate_against_synthetic_parcels(db_session, capsys):
    """A.7 verification: the real `parcels_table1_sample_5000.csv` does not
    exist on this machine (verified before writing this test -- see
    docs/DESIGN_DECISIONS.md), so this reports whatever fit-rates a synthetic
    5000-row set actually produces, instead of asserting the source
    document's specific 62.2% figure. The invariant that must hold
    regardless of the input data: BIKE's tiny 45x45x45cm bay must reject a
    meaningful fraction of parcels that every larger vehicle accepts --
    the dimensional constraint must bind, not be decorative."""
    _seed_real_catalog(db_session)
    catalog = load_catalog_snapshot(db_session, depot_id=None)
    assert len(catalog) == 10

    payloads = generate_synthetic_parcels(
        n=5000, seed=42, n_clusters=6, with_dimensions=True, include_edge_cases=True,
        max_weight_kg=8.0,
    )
    parcels = [
        SimpleNamespace(
            length_cm=p["length_cm"], width_cm=p["width_cm"], height_cm=p["height_cm"],
            volume_m3=p["volume_m3"], loading_orientation_fixed=p["loading_orientation_fixed"],
            dimensions_imputed=False,
        )
        for p in payloads
    ]
    assert max(p.length_cm for p in parcels) >= 115.0, "edge case for longest side must be present"
    assert max(p.volume_m3 for p in parcels) >= 0.663, "edge case for largest volume must be present"

    print(f"\nDimensional fit rates against {len(parcels)} synthetic parcels (Fix Pass 2 A.7):")
    fit_rates = {}
    for vehicle in catalog:
        fit_count = sum(1 for p in parcels if _dimension_fits(p, vehicle))
        rate = fit_count / len(parcels)
        fit_rates[vehicle.code] = rate
        print(f"  {vehicle.code:18s} {vehicle.cargo_length_cm:.0f}x{vehicle.cargo_width_cm:.0f}x"
              f"{vehicle.cargo_height_cm:.0f} cm -> {fit_count}/{len(parcels)} ({rate:.1%})")

    for code in ("APE_CARGO", "TVS_KING", "MICRO_VAN", "VAN_MED", "TRUCK_2T", "TRUCK_4T"):
        assert fit_rates[code] > fit_rates["BIKE"], (
            f"{code} should accept a larger fraction of parcels than BIKE's tiny bay"
        )
    assert fit_rates["BIKE"] < 0.95, "BIKE should genuinely exclude a meaningful fraction of parcels"
