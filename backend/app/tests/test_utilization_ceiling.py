from app.evaluation.utilization_ceiling import compute_utilization_greedy_reference
from app.tests.test_placement import _FakeParcel, _truck_4t


def test_placement_aware_reference_contains_only_verified_loads():
    vehicle = _truck_4t()
    parcels = [_FakeParcel(f"P{i}", 100.0, 100.0, 20.0, 10.0) for i in range(8)]

    result = compute_utilization_greedy_reference(parcels, [vehicle])

    assert result.fleet == [vehicle.code]
    assert sorted(parcel_id for load in result.vehicle_loads for parcel_id in load) == [f"P{i}" for i in range(8)]
    assert 0 < result.utilization <= 1
