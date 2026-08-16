"""Phase 3 gate: the NSGA-II assignment problem must be a genuine
multi-objective search over which parcels share which vehicle and what
type each vehicle is — not the old n_var=1 defect, where `minimize()`'s
result was discarded and distance/compliance were constant across the
whole search space regardless of the decision variable. Replaces
test_baseline_smoke.py's `test_full_pipeline_smoke` as the real gate for
this pipeline stage (per the remediation spec's own note that file is
disposable once this one exists)."""
import random
from datetime import date

from app.optimization.assignment_problem import AssignmentConfig
from app.schemas.parcel import ParcelIn
from app.schemas.vehicle_type import VehicleTypeCatalogIn
from app.services import vehicle_catalog_service
from app.services.data_service import upsert_parcel
from app.services.optimization_service import optimize_load

DEPOT_ID = "DEPOT-1"
DELIVERY_DATE = date(2026, 8, 20)
DEPOT_LAT, DEPOT_LON = 6.9271, 79.8612

FAST_CONFIG = AssignmentConfig(population=30, generations=25, min_parcels_per_vehicle=4, max_vehicle_slots=8)


def _seed_catalog(db_session, specs):
    for code, cap_kg, cap_m3 in specs:
        vehicle_catalog_service.upsert_type(
            db_session,
            VehicleTypeCatalogIn(
                code=code,
                display_name=code,
                capacity_kg=cap_kg,
                capacity_m3=cap_m3,
                cargo_length_cm=200.0,
                cargo_width_cm=150.0,
                cargo_height_cm=150.0,
                max_parcels=100,
                max_stack_layers=4,
                fixed_cost=500.0,
                cost_per_km=20.0,
                avg_speed_kmh=22.0,
                source="test-fixture",
            ),
        )


def _stressed_parcels(db_session, n=20, seed=5):
    """Parcels with varied locations and tight, staggered time windows —
    loose defaults (e.g. a single 09:00-17:00 window for everyone) make
    every candidate trivially 100% compliant and can't exercise objective
    f3 at all."""
    rng = random.Random(seed)
    parcels = []
    for i in range(n):
        lat = DEPOT_LAT + rng.uniform(-0.05, 0.05)
        lon = DEPOT_LON + rng.uniform(-0.05, 0.05)
        start_h = rng.choice([8, 9, 10, 11, 12, 13, 14, 15, 16])
        start_m = rng.choice([0, 30])
        end_m = start_m + 30
        end_h = start_h + (1 if end_m >= 60 else 0)
        end_m %= 60
        payload = ParcelIn(
            parcel_id=f"P{i:04d}",
            depot_id=DEPOT_ID,
            delivery_date=DELIVERY_DATE,
            latitude=lat,
            longitude=lon,
            weight_kg=round(rng.uniform(1.0, 8.0), 2),
            volume_m3=round(rng.uniform(0.01, 0.05), 3),
            time_window_start=f"{start_h:02d}:{start_m:02d}",
            time_window_end=f"{end_h:02d}:{end_m:02d}",
        )
        parcels.append(upsert_parcel(db_session, payload))
    return parcels


def test_front_has_multiple_solutions_and_objectives_genuinely_vary(db_session):
    """The gate: >1 non-dominated solution, and f2 (distance)/f3
    (compliance)/f4 (cost) all take more than one distinct value across the
    front — proof the decision variable actually drives the objectives now,
    unlike the old formulation where two of three objectives were constant."""
    _seed_catalog(db_session, [("SMALL", 30.0, 0.3), ("BIG", 200.0, 2.0)])
    parcels = _stressed_parcels(db_session, n=20, seed=7)

    result, virtual_vehicles = optimize_load(
        db_session, parcels,
        depot_id=DEPOT_ID, depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, delivery_date=DELIVERY_DATE,
        seed=7, config=FAST_CONFIG,
    )

    front = result["pareto_solutions"]
    assert len(front) > 1, "expected more than one non-dominated solution on the front"

    distances = {round(row["estimated_distance_km"], 4) for row in front}
    compliances = {round(row["time_window_compliance"], 4) for row in front}
    costs = {round(row["fleet_cost"], 4) for row in front}
    assert len(distances) > 1, "distance is constant across the front — the old n_var=1 defect"
    assert len(compliances) > 1, "compliance is constant across the front — the old n_var=1 defect"
    assert len(costs) > 1, "fleet cost is constant across the front — the old n_var=1 defect"

    assert virtual_vehicles, "optimize_load must persist at least one VirtualVehicle"
    assert result["virtual_vehicle_ids"]


def test_selected_solution_satisfies_all_constraints(db_session):
    _seed_catalog(db_session, [("SMALL", 30.0, 0.3), ("BIG", 200.0, 2.0)])
    parcels = _stressed_parcels(db_session, n=15, seed=11)

    result, virtual_vehicles = optimize_load(
        db_session, parcels,
        depot_id=DEPOT_ID, depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, delivery_date=DELIVERY_DATE,
        seed=11, config=FAST_CONFIG,
    )

    total_assigned = sum(v.parcel_count for v in virtual_vehicles)
    assert total_assigned == len(parcels), "every parcel must end up on exactly one vehicle"
    for vv in virtual_vehicles:
        assert vv.used_weight_kg <= vv.capacity_kg + 1e-6
        assert vv.used_volume_m3 <= vv.capacity_m3 + 1e-6


def test_fifth_vehicle_type_works_without_code_change(db_session):
    """T is derived from the catalog at runtime — adding a 5th type must
    not require touching assignment_problem.py or optimization_service.py."""
    _seed_catalog(
        db_session,
        [("TYPE_A", 20.0, 0.2), ("TYPE_B", 40.0, 0.4), ("TYPE_C", 60.0, 0.6), ("TYPE_D", 80.0, 0.8), ("TYPE_E", 100.0, 1.0)],
    )
    parcels = _stressed_parcels(db_session, n=12, seed=13)

    result, virtual_vehicles = optimize_load(
        db_session, parcels,
        depot_id=DEPOT_ID, depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, delivery_date=DELIVERY_DATE,
        seed=13, config=FAST_CONFIG,
    )
    assert virtual_vehicles
    used_types = {vv.vehicle_type for vv in virtual_vehicles}
    assert used_types.issubset({"TYPE_A", "TYPE_B", "TYPE_C", "TYPE_D", "TYPE_E"})


def test_seed_is_a_real_caller_supplied_parameter(db_session):
    """Same seed -> identical result; the old code hardcoded seed=42 inside
    `minimize()`, ignoring whatever the caller passed in."""
    _seed_catalog(db_session, [("SMALL", 30.0, 0.3), ("BIG", 200.0, 2.0)])
    parcels = _stressed_parcels(db_session, n=12, seed=17)

    result_a, _ = optimize_load(
        db_session, parcels,
        depot_id=DEPOT_ID, depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, delivery_date=DELIVERY_DATE,
        seed=99, config=FAST_CONFIG,
    )
    result_b, _ = optimize_load(
        db_session, parcels,
        depot_id=DEPOT_ID, depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, delivery_date=DELIVERY_DATE,
        seed=99, config=FAST_CONFIG,
    )

    front_a = sorted(round(row["fleet_cost"], 6) for row in result_a["pareto_solutions"])
    front_b = sorted(round(row["fleet_cost"], 6) for row in result_b["pareto_solutions"])
    assert front_a == front_b, "same seed must reproduce the same Pareto front"


def test_load_plan_and_parcel_assignments_are_persisted(db_session):
    from app.models.load_plan import LoadPlan
    from app.models.parcel_assignment import ParcelAssignment

    _seed_catalog(db_session, [("SMALL", 30.0, 0.3), ("BIG", 200.0, 2.0)])
    parcels = _stressed_parcels(db_session, n=10, seed=23)

    result, virtual_vehicles = optimize_load(
        db_session, parcels,
        depot_id=DEPOT_ID, depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, delivery_date=DELIVERY_DATE,
        seed=23, config=FAST_CONFIG,
    )

    plan = db_session.query(LoadPlan).filter(LoadPlan.plan_id == result["plan_id"]).first()
    assert plan is not None
    assert plan.catalog_snapshot, "catalog_snapshot must record what the optimizer actually saw"
    assert plan.n_parcels == len(parcels)

    assignments = db_session.query(ParcelAssignment).filter(ParcelAssignment.plan_id == plan.plan_id).all()
    assert len(assignments) == len(parcels)
    assigned_parcel_ids = {a.parcel_id for a in assignments}
    assert assigned_parcel_ids == {p.parcel_id for p in parcels}

    for vv in virtual_vehicles:
        vehicle_assignments = [a for a in assignments if a.virtual_vehicle_id == vv.virtual_vehicle_id]
        delivery_sequences = sorted(a.delivery_sequence for a in vehicle_assignments)
        load_sequences = sorted(a.load_sequence for a in vehicle_assignments)
        assert delivery_sequences == list(range(1, len(vehicle_assignments) + 1))
        assert load_sequences == list(range(1, len(vehicle_assignments) + 1))
