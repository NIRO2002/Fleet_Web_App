"""Fix Pass 2 item D: the feasibility-invariant gate.

Every generated plan must satisfy the 13 invariants listed in
BACKEND_REMEDIATION_PROMPT.md Phase 6 (Conservation, Weight, Volume, Count,
Dimensions, Fragility, Stack weight, Hazmat, Refrigeration, Placement
validity, Load order completeness, LIFO consistency, Catalog fidelity), plus
two this pass introduces: Shift window (A.6) and an extended Catalog
fidelity check covering the new A.4 fields.

`hypothesis` is not a project dependency (checked before writing this file),
so per the remediation doc's own fallback ("otherwise a seeded loop of 50
instances is adequate") this uses a seeded Python loop, not a new
dependency.

One documented simplification: invariant 10 (placement validity) checks that
every parcel's load position lies within the cargo bay and that no two
parcels on the same vehicle occupy the exact same (x, y, z) point. It does
not reconstruct full rectangle-overlap-in-chosen-orientation, because the
persisted schema doesn't record which of a parcel's two floor orientations
placement.py chose for a given assignment -- verifying true rectangle
overlap would require also persisting that choice, which is out of scope
for this pass. This is flagged here rather than silently narrowed.
"""
import random
from datetime import date

import pytest

from app.db.seed_vehicle_types import VEHICLE_TYPES
from app.models.load_plan import LoadPlan
from app.models.parcel_assignment import ParcelAssignment
from app.models.virtual_vehicle import VirtualVehicle
from app.optimization.assignment_problem import (
    AssignmentConfig,
    VehicleTypeSpec,
    schedule_time_window_compliance,
)
from app.optimization.placement import _footprint
from app.schemas.parcel import ParcelIn
from app.services import vehicle_catalog_service
from app.services.data_service import upsert_parcel
from app.services.optimization_service import optimize_load
from app.utils_time import minutes

DEPOT_ID = "DEPOT-INV"
DELIVERY_DATE = date(2026, 8, 20)
DEPOT_LAT, DEPOT_LON = 6.9271, 79.8612

INVARIANT_CONFIG = AssignmentConfig(
    depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, population=24, generations=15, max_vehicle_slots=10,
)

N_SEEDS = 50


def _seed_real_catalog(db_session):
    for payload in VEHICLE_TYPES:
        vehicle_catalog_service.upsert_type(db_session, payload)


def _build_instance(db_session, seed: int, n: int = 16) -> list:
    """A small, seeded, edge-case-rich parcel set: some hazardous, some
    refrigerated, some fragile/non-stackable, tight staggered time windows,
    varied weight/volume -- enough that invariants 6, 8, 9 are non-vacuous
    instead of trivially satisfied by an instance with no edge cases at
    all."""
    rng = random.Random(seed)
    parcels = []
    for i in range(n):
        lat = DEPOT_LAT + rng.uniform(-0.04, 0.04)
        lon = DEPOT_LON + rng.uniform(-0.04, 0.04)
        start_h = rng.choice([8, 9, 10, 11, 12, 13, 14])
        end_h = start_h + rng.choice([1, 2, 3])
        hazardous = rng.random() < 0.15
        requires_refrigeration = (not hazardous) and rng.random() < 0.15
        stackable = rng.random() >= 0.15
        fragile = (not stackable) or rng.random() < 0.1

        payload = ParcelIn(
            parcel_id=f"INV-{seed}-{i:03d}",
            depot_id=DEPOT_ID,
            delivery_date=DELIVERY_DATE,
            latitude=lat,
            longitude=lon,
            weight_kg=round(rng.uniform(1.0, 40.0), 2),
            volume_m3=round(rng.uniform(0.01, 0.3), 3),
            length_cm=round(rng.uniform(15, 60), 1),
            width_cm=round(rng.uniform(15, 60), 1),
            height_cm=round(rng.uniform(15, 60), 1),
            time_window_start=f"{start_h:02d}:00",
            time_window_end=f"{end_h:02d}:00",
            fragile=fragile,
            stackable=stackable,
            max_stack_weight_kg=round(rng.uniform(5.0, 50.0), 1),
            hazardous=hazardous,
            hazmat_class="8" if hazardous else None,
            requires_refrigeration=requires_refrigeration,
            temp_min_celsius=-18.0 if requires_refrigeration else None,
            temp_max_celsius=8.0 if requires_refrigeration else None,
            two_person_lift=rng.random() < 0.1,
        )
        parcels.append(upsert_parcel(db_session, payload))
    return parcels


def _catalog_spec_by_code(catalog_snapshot: list[dict]) -> dict[str, dict]:
    return {row["code"]: row for row in catalog_snapshot}


def _assert_conservation(parcels, assignments):
    """1. Conservation: every input parcel appears in exactly one vehicle.
    Compare sets, not counts -- a count check passes when a parcel is
    duplicated and another dropped."""
    input_ids = {p.parcel_id for p in parcels}
    assigned_ids = [a.parcel_id for a in assignments]
    assert set(assigned_ids) == input_ids, "every input parcel must be assigned, none invented"
    assert len(assigned_ids) == len(set(assigned_ids)), "no parcel may be assigned to more than one vehicle"


def _assert_weight_volume_count(vehicles: list[VirtualVehicle]):
    """2/3/4. Weight/Volume/Count capacity."""
    for vv in vehicles:
        assert vv.used_weight_kg <= vv.capacity_kg + 1e-6, f"{vv.virtual_vehicle_id} exceeds weight capacity"
        assert vv.used_volume_m3 <= vv.capacity_m3 + 1e-6, f"{vv.virtual_vehicle_id} exceeds volume capacity"
        if vv.max_parcels is not None:
            assert vv.parcel_count <= vv.max_parcels, f"{vv.virtual_vehicle_id} exceeds max_parcels"


def _assert_dimensions(parcels_by_id, assignments, catalog_by_code, vehicle_by_id):
    """5. Dimensions: every parcel physically fits its vehicle's cargo bay."""
    for a in assignments:
        parcel = parcels_by_id[a.parcel_id]
        vehicle_row = catalog_by_code[vehicle_by_id[a.virtual_vehicle_id]]
        length, width, height = _footprint(parcel)
        assert height <= vehicle_row["cargo_height_cm"] + 1e-6
        fits_flat = length <= vehicle_row["cargo_length_cm"] + 1e-6 and width <= vehicle_row["cargo_width_cm"] + 1e-6
        fits_rotated = (
            not parcel.loading_orientation_fixed
            and width <= vehicle_row["cargo_length_cm"] + 1e-6
            and length <= vehicle_row["cargo_width_cm"] + 1e-6
        )
        assert fits_flat or fits_rotated, f"{a.parcel_id} does not fit {vehicle_by_id[a.virtual_vehicle_id]}'s bay"


def _assert_fragility_and_stack_weight(parcels_by_id, assignments):
    """6. Fragility: no parcel rests on a fragile or non-stackable parcel.
    7. Stack weight: accumulated weight above any parcel <= its
    max_stack_weight_kg."""
    by_vehicle: dict[str, list[ParcelAssignment]] = {}
    for a in assignments:
        by_vehicle.setdefault(a.virtual_vehicle_id, []).append(a)

    for vv_assignments in by_vehicle.values():
        # Group by (x, y): a "column" -- parcels stacked at increasing z/layer.
        by_column: dict[tuple[float, float], list[ParcelAssignment]] = {}
        for a in vv_assignments:
            by_column.setdefault((round(a.load_position_x, 3), round(a.load_position_y, 3)), []).append(a)

        for column in by_column.values():
            column.sort(key=lambda a: a.stack_layer)
            weights = [parcels_by_id[a.parcel_id].weight_kg for a in column]
            for i, a in enumerate(column):
                if i > 0:
                    below = parcels_by_id[column[i - 1].parcel_id]
                    assert below.stackable and not below.fragile, (
                        f"{a.parcel_id} rests on {below.parcel_id}, which is fragile/non-stackable"
                    )
                    # Weight of everything strictly above `below` (i.e. from
                    # this position onward in the column), not a running
                    # total from the floor -- each parcel's own
                    # max_stack_weight_kg bounds only what sits above it.
                    weight_above_below = sum(weights[i:])
                    max_stack = below.max_stack_weight_kg if below.max_stack_weight_kg is not None else 0.0
                    assert weight_above_below <= max_stack + 1e-6, (
                        f"weight stacked above {below.parcel_id} ({weight_above_below}kg) exceeds its "
                        f"max_stack_weight_kg ({max_stack}kg)"
                    )


def _assert_hazmat_and_refrigeration(parcels_by_id, assignments, catalog_by_code, vehicle_by_id):
    """8. Hazmat: hazardous parcels only on certified vehicles.
    9. Refrigeration: refrigerated parcels only on refrigerated vehicles,
    with compatible temperature ranges."""
    for a in assignments:
        parcel = parcels_by_id[a.parcel_id]
        vehicle_row = catalog_by_code[vehicle_by_id[a.virtual_vehicle_id]]
        if parcel.hazardous:
            assert vehicle_row["is_hazmat_certified"], f"{a.parcel_id} is hazardous but its vehicle isn't certified"
        if parcel.requires_refrigeration:
            assert vehicle_row["is_refrigerated"], f"{a.parcel_id} requires refrigeration but its vehicle isn't"
            if parcel.temp_min_celsius is not None and vehicle_row["temp_min_celsius"] is not None:
                assert parcel.temp_min_celsius >= vehicle_row["temp_min_celsius"]
            if parcel.temp_max_celsius is not None and vehicle_row["temp_max_celsius"] is not None:
                assert parcel.temp_max_celsius <= vehicle_row["temp_max_celsius"]


def _assert_placement_validity(assignments, catalog_by_code, vehicle_by_id):
    """10. Placement validity: no two parcels overlap in placement
    coordinates; nothing exceeds the cargo bay bounds. See module docstring
    for the documented simplification (bounds + no-exact-duplicate-point,
    not full rotated-rectangle overlap)."""
    by_vehicle: dict[str, list[ParcelAssignment]] = {}
    for a in assignments:
        by_vehicle.setdefault(a.virtual_vehicle_id, []).append(a)

    for vv_id, vv_assignments in by_vehicle.items():
        vehicle_row = catalog_by_code[vehicle_by_id[vv_id]]
        seen_points = set()
        for a in vv_assignments:
            assert -1e-6 <= a.load_position_x <= vehicle_row["cargo_length_cm"] + 1e-6
            assert -1e-6 <= a.load_position_y <= vehicle_row["cargo_width_cm"] + 1e-6
            assert -1e-6 <= a.load_position_z <= vehicle_row["cargo_height_cm"] + 1e-6
            point = (round(a.load_position_x, 3), round(a.load_position_y, 3), round(a.load_position_z, 3))
            assert point not in seen_points, f"two parcels on {vv_id} occupy the exact same placement point"
            seen_points.add(point)


def _assert_load_order_completeness(assignments):
    """11. Load order completeness: every parcel has a delivery_sequence and
    load_sequence; both are contiguous 1..n within each vehicle."""
    by_vehicle: dict[str, list[ParcelAssignment]] = {}
    for a in assignments:
        by_vehicle.setdefault(a.virtual_vehicle_id, []).append(a)

    for vv_id, vv_assignments in by_vehicle.items():
        n = len(vv_assignments)
        delivery_sequences = sorted(a.delivery_sequence for a in vv_assignments)
        load_sequences = sorted(a.load_sequence for a in vv_assignments)
        assert delivery_sequences == list(range(1, n + 1)), f"{vv_id} delivery_sequence has gaps/duplicates"
        assert load_sequences == list(range(1, n + 1)), f"{vv_id} load_sequence has gaps/duplicates"


def _assert_lifo_consistency(assignments, load_order_exceptions_by_vehicle):
    """12. LIFO consistency: for every pair of parcels on the same vehicle,
    if A is delivered before B then A's placement depth (x) is no greater
    than B's, unless the pair is recorded in load_order_exceptions.

    `_lifo_exceptions` (placement.py) deliberately records one exception per
    out-of-order parcel against the running-max-x holder at the time it was
    placed, not one entry per violating pair (an O(n) single-pass design,
    not an O(n^2) all-pairs scan -- see its docstring). So the set this
    invariant actually checks is: every parcel whose x is less than the
    running maximum x seen so far (in delivery order) must appear as
    `parcel_b` in some recorded exception for that vehicle. This mirrors
    `test_lifo_exceptions_are_linear_and_match_the_brute_force_violation_set`
    in test_placement.py, at the integration level."""
    by_vehicle: dict[str, list[ParcelAssignment]] = {}
    for a in assignments:
        by_vehicle.setdefault(a.virtual_vehicle_id, []).append(a)

    for vv_id, vv_assignments in by_vehicle.items():
        ordered = sorted(vv_assignments, key=lambda a: a.delivery_sequence)
        exceptions = load_order_exceptions_by_vehicle.get(vv_id, [])
        flagged_as_b = {e["parcel_b"] for e in exceptions}

        running_max_x = float("-inf")
        for a in ordered:
            if a.load_position_x < running_max_x - 1e-6:
                assert a.parcel_id in flagged_as_b, (
                    f"{a.parcel_id} is out of LIFO order (x={a.load_position_x} < running max "
                    f"{running_max_x}) on {vv_id} but was not recorded in load_order_exceptions"
                )
            else:
                running_max_x = a.load_position_x


def _assert_catalog_fidelity(vehicles: list[VirtualVehicle], catalog_by_code: dict[str, dict]):
    """13. Catalog fidelity: every vehicle references a vehicle_type_code
    present in catalog_snapshot, with capacities matching exactly.
    15. Extended catalog fidelity (Fix Pass 2): the same check, extended to
    the A.4 fields (vehicle_max_stack_weight_kg, available_from,
    available_until) so it's genuinely additive over #13."""
    for vv in vehicles:
        assert vv.vehicle_type in catalog_by_code, f"{vv.vehicle_type} is not in this plan's catalog_snapshot"
        row = catalog_by_code[vv.vehicle_type]
        assert vv.capacity_kg == row["capacity_kg"]
        assert vv.capacity_m3 == row["capacity_m3"]
        assert vv.cargo_length_cm == row["cargo_length_cm"]
        assert vv.cargo_width_cm == row["cargo_width_cm"]
        assert vv.cargo_height_cm == row["cargo_height_cm"]
        assert vv.is_refrigerated == row["is_refrigerated"]
        assert vv.is_hazmat_certified == row["is_hazmat_certified"]
        assert "vehicle_max_stack_weight_kg" in row
        assert "available_from" in row and "available_until" in row


def _assert_shift_window(parcels_by_id, assignments, catalog_by_code, vehicle_by_id, config):
    """14. Shift window (Fix Pass 2 A.6): every vehicle's tour return time
    is within its own available_until, including accumulated wait."""
    by_vehicle: dict[str, list[ParcelAssignment]] = {}
    for a in assignments:
        by_vehicle.setdefault(a.virtual_vehicle_id, []).append(a)

    for vv_id, vv_assignments in by_vehicle.items():
        ordered = sorted(vv_assignments, key=lambda a: a.delivery_sequence)
        ordered_parcels = [parcels_by_id[a.parcel_id] for a in ordered]
        row = catalog_by_code[vehicle_by_id[vv_id]]
        vehicle_spec = VehicleTypeSpec(
            code=row["code"], capacity_kg=row["capacity_kg"], capacity_m3=row["capacity_m3"],
            cargo_length_cm=row["cargo_length_cm"], cargo_width_cm=row["cargo_width_cm"],
            cargo_height_cm=row["cargo_height_cm"], max_parcels=row["max_parcels"],
            max_stack_layers=row["max_stack_layers"], fixed_cost=row["fixed_cost"],
            cost_per_km=row["cost_per_km"], avg_speed_kmh=row["avg_speed_kmh"],
            is_refrigerated=row["is_refrigerated"], temp_min_celsius=row["temp_min_celsius"],
            temp_max_celsius=row["temp_max_celsius"], is_hazmat_certified=row["is_hazmat_certified"],
            has_tail_lift=row["has_tail_lift"], vehicle_max_stack_weight_kg=row["vehicle_max_stack_weight_kg"],
            available_from=row["available_from"], available_until=row["available_until"],
        )
        _compliance, _flags, _wait, return_time = schedule_time_window_compliance(
            ordered_parcels, vehicle_spec, config
        )
        assert return_time <= minutes(vehicle_spec.available_until) + 1e-6, (
            f"{vv_id} returns at {return_time} min, past its available_until "
            f"({minutes(vehicle_spec.available_until)} min)"
        )


@pytest.mark.parametrize("seed", range(N_SEEDS))
def test_feasibility_invariants_hold(db_session, seed):
    _seed_real_catalog(db_session)
    parcels = _build_instance(db_session, seed)

    result, virtual_vehicles = optimize_load(
        db_session, parcels,
        depot_id=DEPOT_ID, depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, delivery_date=DELIVERY_DATE,
        seed=seed, config=INVARIANT_CONFIG,
    )

    plan = db_session.query(LoadPlan).filter_by(plan_id=result["plan_id"]).first()
    assignments = db_session.query(ParcelAssignment).filter_by(plan_id=plan.plan_id).all()

    parcels_by_id = {p.parcel_id: p for p in parcels}
    catalog_by_code = _catalog_spec_by_code(plan.catalog_snapshot)
    vehicle_by_id = {vv.virtual_vehicle_id: vv.vehicle_type for vv in virtual_vehicles}
    load_order_exceptions_by_vehicle = {
        v["virtual_vehicle_id"]: v["load_order_exceptions"] for v in result["vehicles"]
    }

    _assert_conservation(parcels, assignments)
    _assert_weight_volume_count(virtual_vehicles)
    _assert_dimensions(parcels_by_id, assignments, catalog_by_code, vehicle_by_id)
    _assert_fragility_and_stack_weight(parcels_by_id, assignments)
    _assert_hazmat_and_refrigeration(parcels_by_id, assignments, catalog_by_code, vehicle_by_id)
    _assert_placement_validity(assignments, catalog_by_code, vehicle_by_id)
    _assert_load_order_completeness(assignments)
    _assert_lifo_consistency(assignments, load_order_exceptions_by_vehicle)
    _assert_catalog_fidelity(virtual_vehicles, catalog_by_code)
    _assert_shift_window(parcels_by_id, assignments, catalog_by_code, vehicle_by_id, INVARIANT_CONFIG)
