from copy import deepcopy
from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from app.services.clustering_common import ClusteringConfig, build_feature_matrix, feature_names, project_to_metres
from app.services.clustering_service import cluster


def parcels(n=12):
    return [SimpleNamespace(
        parcel_id=f"P-{i}", depot_id="D-CMB-001", delivery_date=date(2026, 1, 5),
        latitude=6.92 + i * 0.0001, longitude=79.86 + i * 0.0001,
        weight_kg=1 + i, volume_m3=0.01 + i / 1000,
        length_cm=20 + i, width_cm=15 + i, height_cm=10 + i,
        time_window_start="08:00", time_window_end="12:00",
        fragile=bool(i % 2), stackable=not bool(i % 3),
    ) for i in range(n)]


def test_default_features_exclude_every_physical_attribute():
    config = ClusteringConfig(feature_set="location_time")
    assert feature_names(config) == ("projected_x_m", "projected_y_m", "window_midpoint_min")
    original = parcels()
    changed = deepcopy(original)
    for p in changed:
        p.weight_kg *= 100
        p.volume_m3 *= 100
        p.length_cm = p.width_cm = p.height_cm = 999
        p.fragile = not p.fragile
        p.stackable = not p.stackable
    assert np.array_equal(build_feature_matrix(original, config)[0], build_feature_matrix(changed, config)[0])


def test_projection_is_in_metres_without_independent_axis_scaling():
    rows = parcels(2)
    rows[1].latitude = rows[0].latitude + 0.001
    rows[1].longitude = rows[0].longitude
    projected = project_to_metres(rows, 6.9271, 79.8612)
    assert 110 < abs(projected[1, 1] - projected[0, 1]) < 112


def test_time_midpoint_has_explicit_distance_weight():
    rows = parcels(2)
    rows[1].time_window_start = "09:00"
    rows[1].time_window_end = "13:00"
    matrix, _ = build_feature_matrix(rows, ClusteringConfig(feature_set="location_time", time_weight=5))
    assert matrix.shape[1] == 3
    assert matrix[1, 2] - matrix[0, 2] == 300


def test_hdbscan_rejects_mixed_planning_instances():
    rows = parcels()
    rows[-1].depot_id = "D-CMB-002"
    with pytest.raises(ValueError, match="one depot/date"):
        cluster(rows, seed=0)


def test_hdbscan_is_semantically_deterministic():
    first, second = parcels(30), parcels(30)
    physical_before = [(p.parcel_id, p.weight_kg, p.volume_m3, p.length_cm, p.fragile, p.stackable) for p in first]
    config = ClusteringConfig(feature_set="location", min_cluster_size=5, min_samples=3)
    labels_a = cluster(first, seed=7, config=config).labels
    labels_b = cluster(second, seed=7, config=config).labels
    assert np.array_equal(labels_a, labels_b)
    assert {p.parcel_id: p.cluster_id for p in first} == {p.parcel_id: p.cluster_id for p in second}
    assert physical_before == [(p.parcel_id, p.weight_kg, p.volume_m3, p.length_cm, p.fragile, p.stackable) for p in first]
    for grouped in ({p.cluster_id: [] for p in first},):
        for p in first:
            grouped[p.cluster_id].append(p)
        assert all(len({p.depot_id for p in members}) == 1 for members in grouped.values())
        assert all(len({p.delivery_date for p in members}) == 1 for members in grouped.values())
