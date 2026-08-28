from copy import deepcopy
from types import SimpleNamespace

from app.services.clustering_common import ClusteringConfig
from app.services.noise_rescue import assert_complete_cluster_assignment, rescue_noise


LAT, LON = 6.9271, 79.8612


def vehicle(capacity_kg=10):
    return SimpleNamespace(
        capacity_kg=capacity_kg, capacity_m3=2.0, max_parcels=10,
        cargo_length_cm=200, cargo_width_cm=150, cargo_height_cm=150,
        avg_speed_kmh=30, max_stack_layers=3,
        vehicle_max_stack_weight_kg=500,
    )


def parcel(parcel_id, cluster_id, east_km, *, weight=1, side=20):
    return SimpleNamespace(
        parcel_id=parcel_id, cluster_id=cluster_id, is_noise=cluster_id == -1,
        latitude=LAT, longitude=LON + east_km / 110.4,
        weight_kg=weight, volume_m3=side ** 3 / 1_000_000,
        length_cm=side, width_cm=side, height_cm=side,
        time_window_start="08:00", time_window_end="18:00",
        dimensions_imputed=False, loading_orientation_fixed=True,
        do_not_tilt=False, stackable=True, fragile=False,
        cluster_assignment_status=None, noise_resolution=None, unassigned_reason=None,
    )


def test_nearest_infeasible_cluster_is_skipped_for_next_feasible_cluster():
    rows = [parcel("A", 0, 0, weight=9), parcel("B", 1, .4), parcel("N", -1, .1, weight=2)]
    result = rescue_noise(rows, [vehicle()], ClusteringConfig(
        depot_lat=LAT, depot_lon=LON, noise_max_assign_km=1,
    ))
    assert rows[2].cluster_id == 1
    assert rows[2].is_noise is True
    assert rows[2].noise_resolution == "NEAREST_FEASIBLE_CLUSTER"
    assert result.joined_existing_count == 1


def test_noise_joins_nearest_feasible_cluster():
    rows = [parcel("A", 0, 0), parcel("N", -1, .1)]
    result = rescue_noise(rows, [vehicle()], ClusteringConfig(
        depot_lat=LAT, depot_lon=LON, noise_max_assign_km=.2,
    ))
    assert rows[1].cluster_id == 0
    assert rows[1].is_noise is True
    assert result.joined_existing_count == 1


def test_distance_threshold_prevents_forced_existing_cluster_assignment():
    rows = [parcel("A", 0, 0), parcel("N", -1, 1)]
    result = rescue_noise(rows, [vehicle()], ClusteringConfig(
        depot_lat=LAT, depot_lon=LON, noise_max_assign_km=.2, noise_group_max_km=.2,
    ))
    assert result.joined_existing_count == 0
    assert rows[1].cluster_id != 0
    assert rows[1].noise_resolution == "SINGLETON"


def test_group_singleton_and_unresolved_stages_are_honest_and_complete():
    rows = [
        parcel("G1", -1, 0), parcel("G2", -1, .1),
        parcel("S", -1, 2), parcel("X", -1, 4, side=300),
    ]
    result = rescue_noise(rows, [vehicle()], ClusteringConfig(
        depot_lat=LAT, depot_lon=LON, noise_max_assign_km=.01, noise_group_max_km=.3,
    ))
    assert rows[0].cluster_id == rows[1].cluster_id >= 0
    assert {rows[0].noise_resolution, rows[1].noise_resolution} == {"RESCUE_GROUP"}
    assert rows[2].cluster_id >= 0 and rows[2].noise_resolution == "SINGLETON"
    assert rows[3].cluster_id == -1 and rows[3].unassigned_reason == "NO_FITTING_VEHICLE"
    assert result.summary() == {
        "joined_existing_count": 0, "rescue_group_count": 1,
        "rescue_group_parcel_count": 2, "singleton_count": 1, "unresolved_count": 1,
    }
    assert sum(result.summary()[key] for key in (
        "joined_existing_count", "rescue_group_parcel_count", "singleton_count", "unresolved_count",
    )) == 4
    assert_complete_cluster_assignment(rows)


def test_rescue_is_deterministic_and_never_clears_original_noise():
    source = [parcel("B", -1, .1), parcel("A", -1, 0), parcel("C", -1, 2)]
    outputs = []
    for rows in (deepcopy(source), deepcopy(source)):
        rescue_noise(rows, [vehicle()], ClusteringConfig(
            depot_lat=LAT, depot_lon=LON, noise_max_assign_km=.01, noise_group_max_km=.3,
        ))
        outputs.append(sorted((p.parcel_id, p.cluster_id, p.noise_resolution, p.is_noise) for p in rows))
    assert outputs[0] == outputs[1]
    assert all(row[-1] is True for row in outputs[0])
