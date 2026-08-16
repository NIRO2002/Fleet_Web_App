"""Phase 3.5 gate: the placement heuristic must be genuine shelf/FFDH
packing, not the pre-fix row-abandonment defect.

Reproduces defect F3 from the Fix Pass 1 spec: `_open_new_column` locked a
row's depth to whichever parcel happened to open it, so a later, longer
parcel forced a brand-new row even when the current row still had width to
spare. Rows were abandoned after ~2 columns and placement failed just past
100% of the bay's floor area despite `max_stack_layers=5` of headroom going
almost entirely unused.
"""
import random

from app.optimization.assignment_problem import VehicleTypeSpec
from app.optimization.placement import _footprint, attempt_placement


class _FakeParcel:
    def __init__(self, parcel_id, length_cm, width_cm, height_cm, weight_kg):
        self.parcel_id = parcel_id
        self.length_cm = length_cm
        self.width_cm = width_cm
        self.height_cm = height_cm
        self.weight_kg = weight_kg
        self.volume_m3 = (length_cm * width_cm * height_cm) / 1e6
        self.stackable = True
        self.fragile = False
        self.max_stack_weight_kg = 500.0
        self.loading_orientation_fixed = False
        self.latitude = 6.9271
        self.longitude = 79.8612
        self.time_window_start = "09:00"
        self.time_window_end = "17:00"
        self.two_person_lift = False


def _lorry() -> VehicleTypeSpec:
    return VehicleTypeSpec(
        code="LORRY", capacity_kg=5000.0, capacity_m3=25.0,
        cargo_length_cm=550.0, cargo_width_cm=220.0, cargo_height_cm=220.0,
        max_parcels=400, max_stack_layers=5, fixed_cost=6000.0, cost_per_km=85.0,
        avg_speed_kmh=28.0, is_refrigerated=False, temp_min_celsius=None,
        temp_max_celsius=None, is_hazmat_certified=False, has_tail_lift=True,
    )


def test_placement_succeeds_at_three_times_floor_footprint_with_stacking():
    """F3: with everything stackable and a generous stack-weight budget, 5
    layers of headroom should let the bay absorb roughly 3x its own floor
    area — the pre-fix row-abandonment bug failed just past 1x."""
    vehicle = _lorry()
    floor_area = vehicle.cargo_length_cm * vehicle.cargo_width_cm
    parcels = [_FakeParcel(f"P{i:04d}", 40.0, 30.0, 40.0, 5.0) for i in range(400)]
    total_footprint = sum(p.length_cm * p.width_cm for p in parcels)
    assert total_footprint / floor_area >= 3.0, "fixture must actually exercise >=3x floor area"

    result = attempt_placement(parcels, vehicle)

    assert result is not None, "placement should succeed with 5 stacking layers of headroom at 3x floor footprint"


def test_stack_headroom_rejects_a_parcel_exceeding_the_floor_parcels_limit():
    """F4: a stack's weight budget is the floor parcel's `max_stack_weight_kg`
    — a heavy parcel with a generous limit of its own must still be
    rejected from stacking on a column whose *floor* parcel tolerates less,
    not silently placed by checking only its own limit."""
    vehicle = _lorry()
    floor = _FakeParcel("FLOOR", 40.0, 30.0, 20.0, 3.0)
    floor.max_stack_weight_kg = 5.0
    heavy = _FakeParcel("HEAVY", 40.0, 30.0, 20.0, 10.0)
    heavy.max_stack_weight_kg = 100.0  # generous on its own -- must not matter

    # delivery order [HEAVY, FLOOR] -> load order (reverse) processes FLOOR
    # first, so it opens the column and HEAVY is the one being tested.
    result = attempt_placement([heavy, floor], vehicle)

    assert result is not None
    assert result.placements["FLOOR"].layer == 0
    assert result.placements["HEAVY"].layer == 0, (
        "a 10kg parcel must not stack on a column whose floor parcel allows only 5kg, "
        "even though the 10kg parcel's own max_stack_weight_kg is generous"
    )


def test_stack_headroom_accumulates_across_multiple_parcels_in_the_stack():
    """F4: headroom must keep shrinking by everything already stacked, not
    reset to whichever parcel is currently on top — a light parcel with a
    high limit of its own must not reopen the budget for what comes after
    it."""
    vehicle = _lorry()
    floor = _FakeParcel("FLOOR", 40.0, 30.0, 20.0, 3.0)
    floor.max_stack_weight_kg = 5.0
    light = _FakeParcel("LIGHT", 40.0, 30.0, 20.0, 2.0)
    light.max_stack_weight_kg = 100.0  # generous on its own -- must not reopen the budget
    heavy = _FakeParcel("HEAVY2", 40.0, 30.0, 20.0, 4.0)
    heavy.max_stack_weight_kg = 100.0

    # delivery order [HEAVY2, LIGHT, FLOOR] -> load order processes FLOOR,
    # then LIGHT, then HEAVY2, matching the intended stack build-up.
    result = attempt_placement([heavy, light, floor], vehicle)

    assert result is not None
    assert result.placements["FLOOR"].layer == 0
    assert result.placements["LIGHT"].layer == 1, "2kg must fit under the floor parcel's 5kg budget"
    assert result.placements["HEAVY2"].layer == 0, (
        "after LIGHT (2kg) is stacked, only 3kg of headroom remains (5 - 2); "
        "a 4kg parcel must be rejected even though LIGHT's own limit was generous"
    )


def test_lifo_exceptions_are_linear_and_match_the_brute_force_violation_set():
    """F7: the exception scan must be O(n) — one exception per parcel whose
    x is less than the running maximum seen so far in delivery order — not
    the old O(n^2) all-pairs scan that over-counted a single misplaced
    parcel as up to n exceptions."""
    vehicle = _lorry()
    rng = random.Random(7)
    parcels = [
        _FakeParcel(
            f"P{i:04d}", rng.uniform(20, 60), rng.uniform(20, 60), rng.uniform(20, 60), rng.uniform(2, 15)
        )
        for i in range(180)
    ]

    result = attempt_placement(parcels, vehicle)

    assert result is not None
    assert 0 < len(result.load_order_exceptions) < len(parcels), (
        "fixture should produce genuine violations, and stay well under the O(n^2) bound"
    )

    # A parcel is a violation (against the running max) iff some earlier
    # (in delivery order) parcel has a strictly larger x -- recomputed here
    # independently of the production single-pass implementation.
    expected_flagged = set()
    running_max_x = float("-inf")
    for parcel in parcels:
        x = result.placements[parcel.parcel_id].x
        if x < running_max_x:
            expected_flagged.add(parcel.parcel_id)
        else:
            running_max_x = x

    actual_flagged = {e["parcel_b"] for e in result.load_order_exceptions}
    assert actual_flagged == expected_flagged
    assert len(result.load_order_exceptions) == len(expected_flagged), "exactly one exception per violating parcel"


def test_collect_exceptions_false_skips_the_lifo_scan_but_placement_is_unchanged():
    """F7: `collect_exceptions=False` (the GA's constraint-evaluation path)
    must return no exceptions while leaving the actual placement identical
    to the `collect_exceptions=True` (persistence) path."""
    vehicle = _lorry()
    rng = random.Random(7)
    parcels = [
        _FakeParcel(
            f"P{i:04d}", rng.uniform(20, 60), rng.uniform(20, 60), rng.uniform(20, 60), rng.uniform(2, 15)
        )
        for i in range(180)
    ]

    with_exceptions = attempt_placement(parcels, vehicle)
    without_exceptions = attempt_placement(parcels, vehicle, collect_exceptions=False)

    assert with_exceptions.load_order_exceptions, "fixture must actually exercise a violation"
    assert without_exceptions.load_order_exceptions == []
    for parcel in parcels:
        a = with_exceptions.placements[parcel.parcel_id]
        b = without_exceptions.placements[parcel.parcel_id]
        assert (a.x, a.y, a.z, a.layer, a.load_sequence) == (b.x, b.y, b.z, b.layer, b.load_sequence)


def test_footprint_inflates_imputed_dimensions_by_the_safety_factor():
    """F12: a parcel whose stored dimensions are flagged as imputed must
    have its footprint inflated by `imputed_dimension_safety_factor`
    (default 1.5x) before placement — an imputed cube is a guess, not a
    measurement, and should claim more space, not less."""
    real = _FakeParcel("REAL", 20.0, 20.0, 20.0, 5.0)
    real.dimensions_imputed = False
    imputed = _FakeParcel("IMPUTED", 20.0, 20.0, 20.0, 5.0)
    imputed.dimensions_imputed = True

    real_length, real_width, real_height = _footprint(real)
    imputed_length, imputed_width, imputed_height = _footprint(imputed)

    assert (real_length, real_width, real_height) == (20.0, 20.0, 20.0)
    assert (imputed_length, imputed_width, imputed_height) == (30.0, 30.0, 30.0)


def test_placement_failure_reflects_high_floor_utilization_not_row_abandonment():
    """F3 regression guard: if row abandonment reappears, placement fails
    far earlier and leaves most of the floor empty. A real, size-driven
    failure should instead leave the floor mostly (>70%) full."""
    vehicle = _lorry()
    floor_area = vehicle.cargo_length_cm * vehicle.cargo_width_cm
    rng = random.Random(7)
    parcels = [
        _FakeParcel(
            f"P{i:04d}", rng.uniform(20, 60), rng.uniform(20, 60), rng.uniform(20, 60), rng.uniform(2, 15)
        )
        for i in range(180)
    ]

    result = attempt_placement(parcels, vehicle)

    assert result is not None
    floor_occupied = sum(
        p.length_cm * p.width_cm for p in parcels if result.placements[p.parcel_id].layer == 0
    )
    utilization = floor_occupied / floor_area
    assert utilization > 0.70, f"floor utilization {utilization:.1%} is too low — looks like row abandonment"
