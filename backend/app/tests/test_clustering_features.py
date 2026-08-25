from copy import deepcopy
from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from app.services.clustering_common import ClusteringConfig, build_feature_matrix, feature_names, project_to_metres
from app.services.clustering_service import cluster
from app.models.parcel import Parcel
from app.services.capacity_aware_clustering import _fits_some_vehicle, group_by_cluster, repair_clusters
from app.db.seed_vehicle_types import FIELD_DATA_VEHICLE_TYPES
from app.evaluation.clustering_feature_experiment import load_instances


def parcels(n=12):
    return [SimpleNamespace(
        parcel_id=f"P-{i}", depot_id="D-CMB-001", delivery_date=date(2026, 1, 5),
        latitude=6.92 + i * 0.0001, longitude=79.86 + i * 0.0001,
        weight_kg=1 + i, volume_m3=0.01 + i / 1000,
        length_cm=20 + i, width_cm=15 + i, height_cm=10 + i,
        time_window_start="08:00", time_window_end="12:00",
        fragile=bool(i % 2), stackable=not bool(i % 3),
        loading_orientation_fixed=False, do_not_tilt=False,
        max_stack_weight_kg=0.0, two_person_lift=False,
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
        p.max_stack_weight_kg = 999999
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


def test_clustering_and_capacity_repair_are_deterministic_and_conservative():
    source = next(iter(load_instances().values()))

    def run_once():
        rows = [p.model_copy(deep=True) for p in source]
        cluster(rows, seed=11, config=ClusteringConfig())
        repaired = repair_clusters(
            group_by_cluster(rows), FIELD_DATA_VEHICLE_TYPES, seed=11,
        )
        assignment = sorted(
            (parcel.parcel_id, cluster_id)
            for cluster_id, members in repaired.clusters.items()
            for parcel in members
        )
        return rows, repaired, assignment

    first_rows, first, assignment_a = run_once()
    _second_rows, second, assignment_b = run_once()

    assert assignment_a == assignment_b
    assert first.audit == second.audit
    assert all(
        isinstance(row["temporal_split_predicate_fired"], bool)
        for row in first.audit if row["operation"] == "split_check"
    )
    assert {parcel.parcel_id for parcel in first_rows} == {
        parcel.parcel_id for members in first.clusters.values() for parcel in members
    }
    assert len(assignment_a) == len({parcel_id for parcel_id, _ in assignment_a})
    assert all(
        _fits_some_vehicle(members, FIELD_DATA_VEHICLE_TYPES)
        for cluster_id, members in first.clusters.items() if cluster_id >= 0
    )
    if -1 in first.clusters:
        assert first.cluster_status[-1] == {"feasible": False, "reason": "hdbscan_noise"}
        assert all(parcel.cluster_id == -1 for parcel in first.clusters[-1])
    assert first.excluded_infeasible_count == int(-1 in first.clusters)
    assert all(
        row == {"feasible": True, "reason": None}
        for cluster_id, row in first.cluster_status.items() if cluster_id >= 0
    )


def test_capacity_repair_never_mints_clusters_from_noise():
    rows = parcels(4)
    rows[0].cluster_id = rows[1].cluster_id = 3
    rows[2].cluster_id = rows[3].cluster_id = -1

    grouped = group_by_cluster(rows)
    assert grouped[-1] == rows[2:]

    repaired = repair_clusters(grouped, FIELD_DATA_VEHICLE_TYPES, seed=0)
    assert repaired.clusters[-1] == rows[2:]
    assert repaired.cluster_status[-1] == {"feasible": False, "reason": "hdbscan_noise"}
    assert all(parcel.cluster_id == -1 for parcel in rows[2:])
    assert all(parcel not in repaired.clusters.get(0, []) for parcel in rows[2:])


def test_real_priority_is_valid_and_unknown_priority_is_rejected():
    valid = Parcel.model_construct(priority_level="priority")
    assert valid.priority_level == "priority"
    payload = parcels(1)[0].__dict__.copy()
    payload["priority_level"] = "mystery"
    with pytest.raises(ValidationError):
        Parcel.model_validate(payload)


def test_empty_catalog_fails_clearly():
    with pytest.raises(ValueError, match="non-empty vehicle catalog"):
        repair_clusters({0: parcels(2)}, [])
