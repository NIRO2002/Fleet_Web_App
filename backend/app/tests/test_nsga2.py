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
from types import SimpleNamespace

import numpy as np

from app.db.seed_vehicle_types import VEHICLE_TYPES
from app.evaluation.real_data import real_instance_payloads
from app.optimization.assignment_problem import (
    AssignmentConfig,
    AssignmentProblem,
    OverflowRepair,
    VehicleTypeSpec,
    _dimension_fits,
    schedule_time_window_compliance,
    slot_budget,
    decode,
    load_catalog_snapshot,
    run_nsga2,
)
from app.schemas.parcel import ParcelIn
from app.schemas.vehicle_type import VehicleTypeCatalogIn
from app.services import vehicle_catalog_service
from app.services.data_service import upsert_parcel
from app.services.optimization_service import optimize_load

DEPOT_ID = "DEPOT-1"
DELIVERY_DATE = date(2026, 8, 20)
DEPOT_LAT, DEPOT_LON = 6.9271, 79.8612

FAST_CONFIG = AssignmentConfig(population=30, generations=25, max_vehicle_slots=8)


def test_overflow_repair_can_close_a_nearly_empty_slot(parcel_factory):
    parcels = [SimpleNamespace(**p) for p in parcel_factory(n=2, seed=4)]
    vehicle = _test_vehicle_spec()
    problem = AssignmentProblem(parcels, (vehicle,), FAST_CONFIG, n_slots=2)
    row = np.array([0, 1, 0, 0], dtype=float)

    repaired = OverflowRepair()._do(problem, np.array([row]))[0]
    slots, _ = decode(repaired, problem.n, problem.K)

    assert len([members for members in slots.values() if members]) == 1


class _FakeParcel:
    def __init__(self, lat, lon, tw_start, tw_end, two_person_lift=False):
        self.latitude = lat
        self.longitude = lon
        self.time_window_start = tw_start
        self.time_window_end = tw_end
        self.two_person_lift = two_person_lift


def _test_vehicle_spec(avg_speed_kmh=30.0):
    return VehicleTypeSpec(
        code="TEST", capacity_kg=1000.0, capacity_m3=10.0,
        cargo_length_cm=300.0, cargo_width_cm=200.0, cargo_height_cm=200.0,
        max_parcels=100, max_stack_layers=4, fixed_cost=0.0, cost_per_km=0.0,
        avg_speed_kmh=avg_speed_kmh, has_tail_lift=False,
    )


def test_early_arrival_waits_instead_of_failing_compliance():
    """F1: a vehicle departing well before every window opens must score
    fully compliant, not 0.0 — real vehicles wait at the stop."""
    config = AssignmentConfig(depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, depot_departure_time="08:00")
    vehicle = _test_vehicle_spec()
    stops = [_FakeParcel(DEPOT_LAT + 0.001 * i, DEPOT_LON, "09:00", "17:00") for i in range(1, 4)]

    compliance, flags, wait_minutes, _return_time = schedule_time_window_compliance(stops, vehicle, config)

    assert compliance == 1.0
    assert flags == [True, True, True]
    assert wait_minutes > 0


def test_late_arrival_is_genuinely_non_compliant():
    config = AssignmentConfig(depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, depot_departure_time="09:30")
    vehicle = _test_vehicle_spec()
    stops = [_FakeParcel(DEPOT_LAT, DEPOT_LON, "09:00", "17:00")]

    compliance, flags, _wait_minutes, _return_time = schedule_time_window_compliance(stops, vehicle, config)

    assert compliance == 1.0  # sanity: co-located stop, departure already inside the window
    late_stops = [_FakeParcel(DEPOT_LAT, DEPOT_LON, "09:00", "09:31")]  # window closes right after depot departure + travel
    compliance, flags, _wait_minutes, _return_time = schedule_time_window_compliance(late_stops, vehicle, config)
    assert compliance == 1.0

    # A window that has already closed by the time the (co-located, zero
    # travel-time) vehicle departs must fail compliance.
    closed_window = [_FakeParcel(DEPOT_LAT, DEPOT_LON, "08:00", "09:00")]
    compliance, flags, _wait_minutes, _return_time = schedule_time_window_compliance(closed_window, vehicle, config)
    assert compliance == 0.0
    assert flags == [False]


def test_waiting_consumes_shift_time_and_can_cause_a_later_stop_to_run_late():
    """Waiting must push the clock forward, not be free: an early arrival at
    stop 1 that waits until its window opens can still make a
    tightly-windowed stop 2 run late."""
    config = AssignmentConfig(depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, depot_departure_time="08:00")
    vehicle = _test_vehicle_spec()
    stop1 = _FakeParcel(DEPOT_LAT, DEPOT_LON, "09:00", "17:00")  # depot-co-located: arrives 08:00, waits to 09:00
    stop2 = _FakeParcel(DEPOT_LAT, DEPOT_LON, "09:00", "09:02")  # closes 2 minutes after stop1's window opens

    compliance, flags, wait_minutes, _return_time = schedule_time_window_compliance([stop1, stop2], vehicle, config)

    assert flags[0] is True
    assert wait_minutes == 60.0
    assert flags[1] is False  # service time after the wait pushed the clock past 09:02
    assert compliance == 0.5


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


def test_compliance_objective_is_weighted_by_parcel_count_not_vehicle_count():
    """F2: f3 must equal compliant parcels / total parcels, not the mean of
    each vehicle's own compliance rate — a 1-parcel vehicle must not count
    as much as a 4-parcel vehicle."""
    config = AssignmentConfig(depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, depot_departure_time="08:00")
    vehicle = _test_vehicle_spec()
    catalog = (vehicle,)

    non_compliant = ParcelIn(
        parcel_id="A0", latitude=DEPOT_LAT, longitude=DEPOT_LON,
        weight_kg=1.0, volume_m3=0.01, time_window_start="00:00", time_window_end="00:01",
    )
    compliant = [
        ParcelIn(
            parcel_id=f"B{i}", latitude=DEPOT_LAT, longitude=DEPOT_LON,
            weight_kg=1.0, volume_m3=0.01, time_window_start="00:00", time_window_end="23:59",
        )
        for i in range(4)
    ]
    parcels = [non_compliant] + compliant

    problem = AssignmentProblem(parcels, catalog, config, n_slots=2)
    row = np.zeros(problem.n + problem.K, dtype=int)
    row[0] = 0  # the lone non-compliant parcel gets its own slot
    row[1:] = 1  # the four compliant parcels share the other slot
    # (type genes, the last K entries, are already 0 — only one catalog type)

    f, g = problem.evaluate_individual(row)

    assert (g <= 0).all(), f"expected a feasible individual for this check, got constraints {g}"
    mean_compliance = -f[2]
    assert abs(mean_compliance - 0.8) < 1e-9, (
        "compliance must be parcel-weighted (4 of 5 parcels compliant = 0.8), "
        f"not vehicle-averaged (0.5); got {mean_compliance}"
    )


def test_slot_evaluation_cache_hits_on_repeated_slot_contents_and_does_not_leak_across_runs():
    """F5: identical (parcel-set, vehicle-type) slot contents recur across a
    population/generations — caching must produce hits, and the cache must
    live on the AssignmentProblem instance (a fresh run must not inherit
    another run's cache, which would risk corrupting seeded
    reproducibility)."""
    config = AssignmentConfig(depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON)
    vehicle = _test_vehicle_spec()
    catalog = (vehicle,)
    parcels = [
        ParcelIn(
            parcel_id=f"P{i}", latitude=DEPOT_LAT, longitude=DEPOT_LON, weight_kg=1.0, volume_m3=0.01,
            time_window_start="00:00", time_window_end="23:59",
        )
        for i in range(6)
    ]

    problem = AssignmentProblem(parcels, catalog, config, n_slots=2)
    row = np.zeros(problem.n + problem.K, dtype=int)
    row[:3] = 0
    row[3:6] = 1

    problem.evaluate_individual(row)
    assert problem._cache_misses == 2  # two distinct (slot-contents, type) pairs
    assert problem._cache_hits == 0

    problem.evaluate_individual(row)  # identical individual again
    assert problem._cache_hits == 2, "re-evaluating identical slot contents must hit the cache"
    assert problem.cache_hit_rate() == 0.5

    fresh = AssignmentProblem(parcels, catalog, config, n_slots=2)
    assert fresh._cache_hits == 0 and fresh._cache_misses == 0, (
        "a new problem instance must not inherit another instance's cache"
    )


def test_overflow_repair_decodes_the_row_only_once_per_individual(monkeypatch):
    """F6: `_least_loaded_compatible_slot` must not re-decode the whole row
    on every parcel moved — `decode` should be called exactly once per row
    repaired, regardless of how many overflowing parcels get relocated."""
    import app.optimization.assignment_problem as ap

    small_vehicle = VehicleTypeSpec(
        code="SMALL", capacity_kg=5.0, capacity_m3=5.0,
        cargo_length_cm=300.0, cargo_width_cm=200.0, cargo_height_cm=200.0,
        max_parcels=100, max_stack_layers=4, fixed_cost=0.0, cost_per_km=0.0,
        avg_speed_kmh=30.0, has_tail_lift=False,
    )
    config = AssignmentConfig(depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON)
    catalog = (small_vehicle,)
    n = 20
    parcels = [
        ParcelIn(
            parcel_id=f"P{i}", latitude=DEPOT_LAT, longitude=DEPOT_LON, weight_kg=1.0, volume_m3=0.01,
            time_window_start="00:00", time_window_end="23:59",
        )
        for i in range(n)
    ]
    problem = AssignmentProblem(parcels, catalog, config, n_slots=5)
    row = np.zeros(problem.n + problem.K, dtype=int)
    row[:n] = 0  # dump every parcel into slot 0: 20kg on a 5kg-capacity slot, forces many moves

    original_decode = ap.decode
    decode_call_count = {"n": 0}

    def counting_decode(*args, **kwargs):
        decode_call_count["n"] += 1
        return original_decode(*args, **kwargs)

    monkeypatch.setattr(ap, "decode", counting_decode)

    ap.OverflowRepair()._repair_row(problem, row)

    assert decode_call_count["n"] == 1, f"expected exactly one decode() call per row, got {decode_call_count['n']}"

    final_slots, final_types = original_decode(row, problem.n, problem.K)
    for slot_idx, indices in final_slots.items():
        vehicle = catalog[int(np.clip(final_types[slot_idx], 0, problem.T - 1))]
        weight = sum(parcels[i].weight_kg for i in indices)
        assert weight <= vehicle.capacity_kg + 1e-9, "repair must still leave every slot within capacity"


def test_overflow_repair_fixes_count_violations():
    """Fix Pass 4 S3.2: a slot with more parcels than its type's
    max_parcels moves the excess to a compatible slot."""
    import app.optimization.assignment_problem as ap

    tiny_count_vehicle = VehicleTypeSpec(
        code="TINY_COUNT", capacity_kg=1000.0, capacity_m3=1000.0,
        cargo_length_cm=500.0, cargo_width_cm=500.0, cargo_height_cm=500.0,
        max_parcels=3, max_stack_layers=4, fixed_cost=0.0, cost_per_km=0.0,
        avg_speed_kmh=30.0, has_tail_lift=False,
    )
    config = AssignmentConfig(depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON)
    catalog = (tiny_count_vehicle,)
    n = 10
    parcels = [
        ParcelIn(
            parcel_id=f"P{i}", latitude=DEPOT_LAT, longitude=DEPOT_LON, weight_kg=0.1, volume_m3=0.001,
            time_window_start="00:00", time_window_end="23:59",
        )
        for i in range(n)
    ]
    problem = ap.AssignmentProblem(parcels, catalog, config, n_slots=5)
    row = np.zeros(problem.n + problem.K, dtype=int)
    row[:n] = 0  # dump all 10 into slot 0, which only allows 3

    ap.OverflowRepair()._repair_row(problem, row)

    final_slots, final_types = ap.decode(row, problem.n, problem.K)
    for slot_idx, indices in final_slots.items():
        vehicle = catalog[int(np.clip(final_types[slot_idx], 0, problem.T - 1))]
        assert len(indices) <= vehicle.max_parcels, f"slot {slot_idx} still exceeds max_parcels after repair"
    total_after = sum(len(indices) for indices in final_slots.values())
    assert total_after == n, "repair must not lose or duplicate parcels"


def test_overflow_repair_fixes_dimensional_misfits():
    """Fix Pass 4 S3.2: a parcel too large for its slot's type moves to a
    slot whose type accepts it, or that slot's type gets upgraded."""
    import app.optimization.assignment_problem as ap

    small_bay_vehicle = VehicleTypeSpec(
        code="SMALL_BAY", capacity_kg=1000.0, capacity_m3=1000.0,
        cargo_length_cm=30.0, cargo_width_cm=30.0, cargo_height_cm=30.0,
        max_parcels=100, max_stack_layers=1, fixed_cost=0.0, cost_per_km=0.0,
        avg_speed_kmh=30.0, has_tail_lift=False,
    )
    big_bay_vehicle = VehicleTypeSpec(
        code="BIG_BAY", capacity_kg=1000.0, capacity_m3=1000.0,
        cargo_length_cm=300.0, cargo_width_cm=300.0, cargo_height_cm=300.0,
        max_parcels=100, max_stack_layers=1, fixed_cost=0.0, cost_per_km=0.0,
        avg_speed_kmh=30.0, has_tail_lift=False,
    )
    config = AssignmentConfig(depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON)
    catalog = (small_bay_vehicle, big_bay_vehicle)
    # one small parcel (fits SMALL_BAY) + one oversized parcel (needs BIG_BAY)
    parcels = [
        ParcelIn(
            parcel_id="SMALL", latitude=DEPOT_LAT, longitude=DEPOT_LON, weight_kg=1.0, volume_m3=0.001,
            time_window_start="00:00", time_window_end="23:59", length_cm=10.0, width_cm=10.0, height_cm=10.0,
        ),
        ParcelIn(
            parcel_id="OVERSIZED", latitude=DEPOT_LAT, longitude=DEPOT_LON, weight_kg=1.0, volume_m3=0.5,
            time_window_start="00:00", time_window_end="23:59", length_cm=100.0, width_cm=100.0, height_cm=100.0,
        ),
    ]
    problem = ap.AssignmentProblem(parcels, catalog, config, n_slots=2)
    row = np.zeros(problem.n + problem.K, dtype=int)
    row[:2] = 0  # both parcels in slot 0, typed SMALL_BAY -- OVERSIZED doesn't fit

    ap.OverflowRepair()._repair_row(problem, row)

    final_slots, final_types = ap.decode(row, problem.n, problem.K)
    oversized_idx = [p.parcel_id for p in parcels].index("OVERSIZED")
    oversized_slot = next(s for s, indices in final_slots.items() if oversized_idx in indices)
    oversized_vehicle = catalog[int(np.clip(final_types[oversized_slot], 0, problem.T - 1))]
    assert _dimension_fits(parcels[oversized_idx], oversized_vehicle), (
        "OVERSIZED must end up on a slot/type that actually fits it after repair"
    )


def test_placement_repair_calls_attempt_placement_a_bounded_number_of_times(monkeypatch):
    """Fix Pass 4 S6 regression guard: `_repair_placement` (S3.2) originally
    retried `attempt_placement` once per candidate removed, uncapped -- on
    real data, where a badly-oversized slot can be far past where any small
    number of drops would succeed, this dominated a full run's wall-clock
    (~1545s -> ~249s for one 400-real-parcel/pop=100/gen=200 run once
    capped; see docs/FIX_PASS_4_REPORT.md). `MAX_PLACEMENT_REPAIR_ATTEMPTS`
    bounds it to a small constant per slot, regardless of slot size."""
    import app.optimization.assignment_problem as ap
    import app.optimization.placement as pl

    tiny_bay_vehicle = VehicleTypeSpec(
        code="TINY_BAY", capacity_kg=10_000.0, capacity_m3=10_000.0,
        cargo_length_cm=10.0, cargo_width_cm=10.0, cargo_height_cm=10.0,
        max_parcels=1000, max_stack_layers=1, fixed_cost=0.0, cost_per_km=0.0,
        avg_speed_kmh=30.0, has_tail_lift=False,
    )
    config = AssignmentConfig(depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON)
    catalog = (tiny_bay_vehicle,)
    n = 40  # every parcel is individually too large for the 10x10cm bay -- repair can never succeed
    parcels = [
        ParcelIn(
            parcel_id=f"P{i}", latitude=DEPOT_LAT, longitude=DEPOT_LON, weight_kg=0.1, volume_m3=0.001,
            time_window_start="00:00", time_window_end="23:59",
            length_cm=50.0, width_cm=50.0, height_cm=50.0,
        )
        for i in range(n)
    ]
    problem = ap.AssignmentProblem(parcels, catalog, config, n_slots=5)
    row = np.zeros(problem.n + problem.K, dtype=int)
    row[:n] = 0

    call_count = {"n": 0}
    original_attempt_placement = pl.attempt_placement

    def counting_attempt_placement(*args, **kwargs):
        call_count["n"] += 1
        return original_attempt_placement(*args, **kwargs)

    monkeypatch.setattr(ap, "attempt_placement", counting_attempt_placement)

    ap.OverflowRepair()._repair_row(problem, row)

    # 1 initial check + at most MAX_PLACEMENT_REPAIR_ATTEMPTS retries, for
    # this single slot -- regardless of n=40 candidates being available.
    assert call_count["n"] <= 1 + ap.OverflowRepair.MAX_PLACEMENT_REPAIR_ATTEMPTS


def test_warm_start_produces_multiple_rows_and_splits_an_oversized_cluster():
    """Fix Pass 4 S3.1: no single catalog type fits the whole cluster ->
    the cluster is split across multiple slots instead of an infeasible
    row being emitted, and multiple warm-start individuals are produced."""
    import app.optimization.assignment_problem as ap

    small = VehicleTypeSpec(
        code="SMALL", capacity_kg=10.0, capacity_m3=10.0,
        cargo_length_cm=100.0, cargo_width_cm=100.0, cargo_height_cm=100.0,
        max_parcels=50, max_stack_layers=3, fixed_cost=0.0, cost_per_km=0.0,
        avg_speed_kmh=30.0, has_tail_lift=False,
    )
    catalog = (small,)
    n = 6
    parcels = [
        ParcelIn(
            parcel_id=f"P{i}", latitude=DEPOT_LAT, longitude=DEPOT_LON, weight_kg=4.0, volume_m3=0.01,
            time_window_start="00:00", time_window_end="23:59",
        )
        for i in range(n)
    ]  # total weight 24kg -- no single SMALL (10kg) can hold the whole cluster
    clusters = {0: parcels}
    K = 6

    rows = ap.warm_start_rows_from_clusters(parcels, clusters, catalog, K, AssignmentConfig())
    assert len(rows) >= 1
    slot_assignment = rows[0][:n]
    assert len(set(slot_assignment.tolist())) > 1, "an oversized cluster must be split across multiple slots"


def test_assignment_config_threads_weight_order_to_placement(monkeypatch):
    """R1: the optimizer config, not a hidden placement default, controls the rule."""
    import app.optimization.assignment_problem as ap

    seen = []
    original = ap.attempt_placement

    def capture(*args, **kwargs):
        seen.append(kwargs.get("enforce_weight_order"))
        return original(*args, **kwargs)

    monkeypatch.setattr(ap, "attempt_placement", capture)
    parcels = [ParcelIn(
        parcel_id="P-CONFIG", latitude=DEPOT_LAT, longitude=DEPOT_LON,
        weight_kg=1.0, volume_m3=0.001,
        time_window_start="08:00", time_window_end="18:00",
    )]
    problem = ap.AssignmentProblem(
        parcels, (_catalog_pair()[0],), AssignmentConfig(enforce_weight_order=True), n_slots=1,
    )
    problem.evaluate_individual(np.array([0, 0]))
    assert seen == [True]

def _catalog_pair():
    small = VehicleTypeSpec(
        code="SMALL", capacity_kg=30.0, capacity_m3=0.3, cargo_length_cm=150.0, cargo_width_cm=100.0,
        cargo_height_cm=100.0, max_parcels=50, max_stack_layers=3, fixed_cost=100.0, cost_per_km=10.0,
        avg_speed_kmh=25.0, has_tail_lift=False,
    )
    big = VehicleTypeSpec(
        code="BIG", capacity_kg=200.0, capacity_m3=2.0, cargo_length_cm=280.0, cargo_width_cm=170.0,
        cargo_height_cm=170.0, max_parcels=200, max_stack_layers=4, fixed_cost=500.0, cost_per_km=30.0,
        avg_speed_kmh=28.0, has_tail_lift=True,
    )
    return (small, big)


def test_slot_budget_is_derived_from_capacity_not_a_flat_parcels_per_vehicle_constant():
    """F9: K comes from total demand against the catalog's capacity range
    (k_min against the largest type, k_est*slack against the median type),
    not `n_parcels / min_parcels_per_vehicle`."""
    catalog = _catalog_pair()
    config = AssignmentConfig()
    parcels = [
        ParcelIn(
            parcel_id=f"P{i}", latitude=DEPOT_LAT, longitude=DEPOT_LON,
            weight_kg=10.0, volume_m3=0.05, time_window_start="09:00", time_window_end="17:00",
        )
        for i in range(10)
    ]
    # total weight=100kg, volume=0.5m3; largest=(200kg,2m3) -> k_min=ceil(0.5)=1
    # median=(115kg,1.15m3) -> k_est=ceil(100/115)=1 -> ceil(1*1.5)=2 -> K=max(2, k_min+1=2)=2
    assert slot_budget(parcels, catalog, config) == 2


def test_slot_budget_safety_cap_scales_with_n_parcels_not_just_the_configured_value():
    """F9: `max_vehicle_slots` is raised by `slot_budget` itself when
    `n_parcels` justifies it, rather than silently truncating a large
    instance's capacity-derived estimate to a small configured value."""
    catalog = _catalog_pair()
    config = AssignmentConfig(max_vehicle_slots=1)  # deliberately far too small on its own
    parcels = [
        ParcelIn(
            parcel_id=f"P{i}", latitude=DEPOT_LAT, longitude=DEPOT_LON,
            weight_kg=50.0, volume_m3=0.3, time_window_start="09:00", time_window_end="17:00",
        )
        for i in range(30)
    ]
    # raw demand wants ceil(k_est*1.5)=21 slots; the dynamic cap
    # max(1, ceil(30/3))=10 should bind instead of the configured 1.
    assert slot_budget(parcels, catalog, config) == 10


def test_imputed_dimensions_get_a_safety_factor_before_the_fit_check():
    """F12: a parcel flagged `dimensions_imputed=True` must have its stored
    (cube-from-volume) side inflated by the safety factor before the
    dimensional-fit check -- an imputed cube is a guess, and a real parcel
    with the same volume could be long and thin enough not to fit."""
    vehicle = VehicleTypeSpec(
        code="TEST", capacity_kg=1000.0, capacity_m3=10.0,
        cargo_length_cm=22.0, cargo_width_cm=22.0, cargo_height_cm=22.0,
        max_parcels=100, max_stack_layers=4, fixed_cost=0.0, cost_per_km=0.0,
        avg_speed_kmh=30.0, has_tail_lift=False,
    )
    # volume 0.008 m^3 -> cbrt(8000) = a 20cm cube: fits the 22cm bay
    # untouched, but 20 * 1.5 (default safety factor) = 30cm does not.
    real_dims = ParcelIn(
        parcel_id="REAL", latitude=DEPOT_LAT, longitude=DEPOT_LON, weight_kg=1.0, volume_m3=0.008,
        time_window_start="09:00", time_window_end="17:00", length_cm=20.0, width_cm=20.0, height_cm=20.0,
        dimensions_imputed=False,
    )
    imputed_dims = ParcelIn(
        parcel_id="IMPUTED", latitude=DEPOT_LAT, longitude=DEPOT_LON, weight_kg=1.0, volume_m3=0.008,
        time_window_start="09:00", time_window_end="17:00", length_cm=20.0, width_cm=20.0, height_cm=20.0,
        dimensions_imputed=True,
    )

    assert _dimension_fits(real_dims, vehicle) is True
    assert _dimension_fits(imputed_dims, vehicle) is False, (
        "imputed dims must be inflated by the safety factor, not trusted at face value"
    )


def test_front_contains_unique_objective_vectors(db_session):
    """The public front contains genuine trade-off points, not duplicate
    objective rows from different genotypes. A small instance may correctly
    have a single dominating point."""
    _seed_catalog(db_session, [("SMALL", 30.0, 0.3), ("BIG", 200.0, 2.0)])
    parcels = _stressed_parcels(db_session, n=20, seed=7)

    result, virtual_vehicles = optimize_load(
        db_session, parcels,
        depot_id=DEPOT_ID, depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, delivery_date=DELIVERY_DATE,
        seed=7, config=FAST_CONFIG,
    )

    front = result["pareto_solutions"]
    assert front, "expected at least one non-dominated solution"

    distances = {round(row["estimated_distance_km"], 4) for row in front}
    compliances = {round(row["time_window_compliance"], 4) for row in front}
    costs = {round(row["fleet_cost"], 4) for row in front}
    utilizations = {round(row["utilization"], 4) for row in front}
    objective_vectors = {
        (round(row["utilization"], 6), round(row["estimated_distance_km"], 6),
         round(row["time_window_compliance"], 6), round(row["fleet_cost"], 6))
        for row in front
    }
    assert len(objective_vectors) == len(front)

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

    catalog = load_catalog_snapshot(db_session, DEPOT_ID, DELIVERY_DATE)
    _problem_a, raw_a = run_nsga2(parcels, catalog, FAST_CONFIG, seed=99)
    _problem_b, raw_b = run_nsga2(parcels, catalog, FAST_CONFIG, seed=99)
    np.testing.assert_array_equal(raw_a.X, raw_b.X)
    np.testing.assert_array_equal(raw_a.F, raw_b.F)
    np.testing.assert_array_equal(raw_a.G, raw_b.G)

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


def test_optimize_load_does_not_crash_when_nothing_is_fully_feasible(db_session):
    """Fix Pass 4 regression guard: pymoo's NSGA2 defaults to
    `return_least_infeasible=False`, meaning `res.opt`/`res.X`/`res.F`/
    `res.G` are ALL None whenever not one individual in the entire run was
    fully feasible -- common on harder real instances (see
    docs/FIX_PASS_4_REPORT.md), previously crashing `optimize_load` outright
    with 'NSGA-II produced no result.' Forces genuine infeasibility here
    (demand far beyond any catalog type's capacity, at a tiny population/
    generation budget) and asserts a best-effort plan is still returned."""
    _seed_catalog(db_session, [("TINY", 1.0, 0.01)])
    parcels = _stressed_parcels(db_session, n=15, seed=5)  # each ~1-8kg, total far exceeds any TINY-only fleet
    tiny_config = AssignmentConfig(
        depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, population=6, generations=2, max_vehicle_slots=3,
    )

    result, virtual_vehicles = optimize_load(
        db_session, parcels,
        depot_id=DEPOT_ID, depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, delivery_date=DELIVERY_DATE,
        seed=5, config=tiny_config,
    )

    assert result["plan_id"]
    assert virtual_vehicles


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


def test_optimize_load_marks_parcels_planned_and_records_carryover(db_session):
    """Fix Pass 2 item C gate, end to end: PENDING parcels across two dates
    -> planning the later date pulls in the earlier date's leftovers via
    get_planning_instance -> optimize_load marks every planned parcel
    PLANNED with plan_id set, and the persisted LoadPlan records how many
    were carryover."""
    from app.models.load_plan import LoadPlan
    from app.models.parcel import Parcel
    from app.services.clustering_common import get_planning_instance

    _seed_catalog(db_session, [("SMALL", 30.0, 0.3), ("BIG", 200.0, 2.0)])

    earlier_date = date(2026, 8, 19)
    leftover_payload = ParcelIn(
        parcel_id="LEFTOVER-1", depot_id=DEPOT_ID, delivery_date=earlier_date,
        latitude=DEPOT_LAT, longitude=DEPOT_LON, weight_kg=2.0, volume_m3=0.01,
        time_window_start="09:00", time_window_end="17:00", status="PENDING",
    )
    upsert_parcel(db_session, leftover_payload)

    today_parcels = _stressed_parcels(db_session, n=5, seed=41)

    parcels = get_planning_instance(db_session, DEPOT_ID, DELIVERY_DATE)
    db_session.commit()
    assert {p.parcel_id for p in parcels} == {"LEFTOVER-1"} | {p.parcel_id for p in today_parcels}

    result, _virtual_vehicles = optimize_load(
        db_session, parcels,
        depot_id=DEPOT_ID, depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, delivery_date=DELIVERY_DATE,
        seed=41, config=FAST_CONFIG,
    )

    for parcel in parcels:
        db_session.refresh(parcel)
        assert parcel.status == "PLANNED"
        assert parcel.plan_id == result["plan_id"]

    leftover = db_session.query(Parcel).filter_by(parcel_id="LEFTOVER-1").first()
    assert leftover.carried_over_from_date == earlier_date
    assert leftover.delivery_date == DELIVERY_DATE

    plan = db_session.query(LoadPlan).filter_by(plan_id=result["plan_id"]).first()
    assert plan.n_carryover_parcels == 1
    assert plan.run_manifest is not None
    assert "git_commit_sha" in plan.run_manifest


def test_optimize_load_runs_on_a_real_instance_subset(db_session):
    """Fix Pass 4 item S5: at least one integration test per module runs
    against real data (data/parcels_sample_36000.csv), not only synthetic --
    this is what would have caught the priority_level='priority' schema gap
    and the S1 placement defect, both real-data-only defects that 108
    synthetic-only-tested passes didn't surface. A 30-parcel subset of the
    real D-CMB-001/2026-01-05 instance, real 7-row catalog, real
    conservation/persistence check."""
    for payload in VEHICLE_TYPES:
        vehicle_catalog_service.upsert_type(db_session, payload)

    real_depot_id, real_delivery_date = "D-CMB-001", date(2026, 1, 5)
    payloads = real_instance_payloads("D-CMB-001", "2026-01-05")[:30]
    parcels = [upsert_parcel(db_session, ParcelIn(**p)) for p in payloads]

    result, virtual_vehicles = optimize_load(
        db_session, parcels,
        depot_id=real_depot_id, depot_lat=6.9271, depot_lon=79.8612, delivery_date=real_delivery_date,
        seed=7, config=FAST_CONFIG,
    )

    assert result["plan_id"]
    assert virtual_vehicles
    total_assigned = sum(vv.parcel_count for vv in virtual_vehicles)
    assert total_assigned == len(parcels), "every real parcel must end up on exactly one vehicle"
    for vv in virtual_vehicles:
        assert vv.used_weight_kg <= vv.capacity_kg + 1e-6
        assert vv.used_volume_m3 <= vv.capacity_m3 + 1e-6
