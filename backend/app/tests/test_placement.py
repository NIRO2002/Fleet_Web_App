from types import SimpleNamespace

from app.optimization.placement import (
    Placement, PlacementResult, _assign_physical_load_sequence,
    _insertion_path_blocked, attempt_placement, validate_loading_sequence,
)


def vehicle(**overrides):
    values = dict(cargo_length_cm=150.0, cargo_width_cm=100.0, cargo_height_cm=100.0,
                  max_stack_layers=3, vehicle_max_stack_weight_kg=500.0)
    values.update(overrides)
    return SimpleNamespace(**values)


def parcel(parcel_id, length, width, height=20, **overrides):
    values = dict(parcel_id=parcel_id, length_cm=length, width_cm=width, height_cm=height,
                  volume_m3=length * width * height / 1_000_000, weight_kg=10.0,
                  dimensions_imputed=False, loading_orientation_fixed=True, do_not_tilt=False,
                  stackable=True, fragile=False)
    values.update(overrides)
    return SimpleNamespace(**values)


def placed(parcel_id, x, y, z=0, length=20, width=20, height=20):
    return Placement(parcel_id, x, y, z, int(z > 0), 0, length, width, height)


def test_deep_parcel_precedes_near_door_blocker():
    deep, near = placed("DEEP", 80, 0), placed("NEAR", 20, 0)
    placements = {p.parcel_id: p for p in (deep, near)}
    assert _insertion_path_blocked(deep, near)
    assert _assign_physical_load_sequence([SimpleNamespace(parcel_id="DEEP"), SimpleNamespace(parcel_id="NEAR")], placements, {})
    assert deep.load_sequence < near.load_sequence


def test_side_by_side_near_parcel_is_not_a_blocker():
    deep, near = placed("DEEP", 80, 0, width=20), placed("NEAR", 20, 30, width=20)
    assert not _insertion_path_blocked(deep, near)


def test_deep_row_reuse_gets_reachable_sequence():
    rows = [parcel("DEEP-A", 70, 60), parcel("NEAR", 40, 100), parcel("DEEP-B", 30, 30, height=90)]
    result = attempt_placement(rows, vehicle())
    assert result is not None
    deep_b, near = result.placements["DEEP-B"], result.placements["NEAR"]
    assert deep_b.x > near.x
    assert _insertion_path_blocked(deep_b, near)
    assert deep_b.load_sequence < near.load_sequence
    assert validate_loading_sequence(rows, vehicle(), result)


def test_stack_support_precedes_top_despite_lifo_preference():
    top = parcel("TOP", 30, 30, 20, weight_kg=5)
    base = parcel("BASE", 40, 40, 20, weight_kg=20)
    result = attempt_placement([base, top], vehicle(cargo_width_cm=40))
    assert result is not None
    assert result.placements["BASE"].load_sequence < result.placements["TOP"].load_sequence


def test_blocker_at_stack_height_blocks_deep_target():
    target = placed("TARGET", 80, 0, z=30, length=20, width=20, height=20)
    blocker = placed("BLOCKER", 20, 0, z=35, length=20, width=20, height=10)
    assert _insertion_path_blocked(target, blocker)


def test_low_near_parcel_does_not_block_high_insertion_corridor():
    target = placed("TARGET", 80, 0, z=30, length=20, width=20, height=20)
    blocker = placed("LOW", 20, 0, z=0, length=20, width=20, height=20)
    assert not _insertion_path_blocked(target, blocker)


def test_complete_sequence_validation_and_integrity():
    rows = [parcel("A", 50, 50), parcel("B", 40, 40), parcel("C", 30, 30)]
    result = attempt_placement(rows, vehicle())
    assert result is not None
    assert validate_loading_sequence(rows, vehicle(), result)
    assert sorted(p.load_sequence for p in result.placements.values()) == [1, 2, 3]
    assert result.physical_load_order_valid is True


def test_existing_simple_layout_remains_feasible():
    rows = [parcel("A", 40, 40), parcel("B", 40, 40)]
    assert attempt_placement(rows, vehicle()) is not None


def test_stacked_parcel_keeps_its_actual_oriented_dimensions():
    base = parcel("BASE", 60, 60, weight_kg=20)
    top = parcel("TOP", 30, 20, weight_kg=5)
    result = attempt_placement([top, base], vehicle(cargo_width_cm=60))
    assert result is not None
    top_placement = result.placements["TOP"]
    assert (top_placement.placed_length_cm, top_placement.placed_width_cm) == (30, 20)
    assert top_placement.layer == 1
