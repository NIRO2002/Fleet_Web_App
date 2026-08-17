"""Phase 2 gate: noise handling, planning-instance scoping, scaler
determinism, and HDBSCAN/K-Means interface parity."""
import random
from datetime import date

import numpy as np
import pytest

from app.services import baseline_clustering, clustering_service
from app.services.clustering_common import ClusteringConfig, get_planning_instance, handle_noise
from app.models.parcel import Parcel


def _make_parcel(parcel_id, lat, lon, depot_id="D1", delivery_date=date(2026, 8, 20), **overrides):
    defaults = dict(
        parcel_id=parcel_id,
        depot_id=depot_id,
        delivery_date=delivery_date,
        latitude=lat,
        longitude=lon,
        weight_kg=2.0,
        volume_m3=0.01,
        time_window_start="10:00",
        time_window_end="13:00",
        fragile=False,
        priority_level="standard",
    )
    defaults.update(overrides)
    return Parcel(**defaults)


def _tight_two_cluster_instance(db_session, n_per_cluster=10, depot_id="D1", delivery_date=date(2026, 8, 20)):
    rng = random.Random(7)
    centers = [(6.90, 79.85), (6.95, 79.90)]
    for c_idx, (clat, clon) in enumerate(centers):
        for i in range(n_per_cluster):
            p = _make_parcel(
                f"C{c_idx}-{i:03d}",
                clat + rng.uniform(-0.001, 0.001),
                clon + rng.uniform(-0.001, 0.001),
                depot_id=depot_id,
                delivery_date=delivery_date,
            )
            db_session.add(p)
    db_session.commit()


def test_get_planning_instance_scopes_to_depot_and_date(db_session):
    _tight_two_cluster_instance(db_session, depot_id="D1", delivery_date=date(2026, 8, 20))
    # a decoy parcel in a different instance must never be returned
    db_session.add(_make_parcel("OTHER", 6.90, 79.85, depot_id="D2", delivery_date=date(2026, 8, 21)))
    db_session.commit()

    instance = get_planning_instance(db_session, "D1", date(2026, 8, 20))
    assert len(instance) == 20
    assert all(p.depot_id == "D1" for p in instance)

    other = get_planning_instance(db_session, "D2", date(2026, 8, 21))
    assert len(other) == 1


def test_get_planning_instance_carries_over_leftover_pending_parcels(db_session):
    """Fix Pass 2 item C gate: PENDING/FAILED parcels from an earlier date
    at the same depot are included when planning a later date, marked with
    carried_over_from_date, and their delivery_date is rolled forward --
    but their time windows are left untouched (not this system's decision
    to make)."""
    earlier = _make_parcel(
        "LEFTOVER-1", 6.90, 79.85, depot_id="D1", delivery_date=date(2026, 8, 19),
        time_window_start="09:00", time_window_end="11:00", status="PENDING",
    )
    delivered_already = _make_parcel(
        "ALREADY-DELIVERED", 6.90, 79.85, depot_id="D1", delivery_date=date(2026, 8, 19), status="DELIVERED",
    )
    today = _make_parcel("TODAY-1", 6.91, 79.86, depot_id="D1", delivery_date=date(2026, 8, 20), status="PENDING")
    db_session.add_all([earlier, delivered_already, today])
    db_session.commit()

    instance = get_planning_instance(db_session, "D1", date(2026, 8, 20))
    ids = {p.parcel_id for p in instance}
    assert ids == {"LEFTOVER-1", "TODAY-1"}, "DELIVERED parcels must never be carried over"

    leftover = next(p for p in instance if p.parcel_id == "LEFTOVER-1")
    assert leftover.delivery_date == date(2026, 8, 20)
    assert leftover.carried_over_from_date == date(2026, 8, 19)
    assert leftover.time_window_start == "09:00", "time windows must not be silently rewritten"

    today_parcel = next(p for p in instance if p.parcel_id == "TODAY-1")
    assert today_parcel.carried_over_from_date is None

    no_carryover = get_planning_instance(db_session, "D1", date(2026, 8, 20), include_carryover=False)
    assert {p.parcel_id for p in no_carryover} == {"TODAY-1"}


def test_hdbscan_finds_distinct_clusters_and_resolves_noise(db_session):
    _tight_two_cluster_instance(db_session)
    parcels = get_planning_instance(db_session, "D1", date(2026, 8, 20))
    config = ClusteringConfig(min_cluster_size=5, min_samples=3)

    result = clustering_service.cluster(parcels, seed=0, config=config)

    assert result.method == "hdbscan"
    assert result.n_clusters >= 1
    assert all(label != -1 for label in result.labels), "noise (-1) must never survive as a pseudo-cluster"
    # every parcel's is_noise flag was set (even if False)
    assert all(hasattr(p, "is_noise") for p in parcels)


def test_hdbscan_scaler_is_deterministic_for_a_fixed_seed(db_session):
    _tight_two_cluster_instance(db_session)
    parcels_a = get_planning_instance(db_session, "D1", date(2026, 8, 20))
    parcels_b = get_planning_instance(db_session, "D1", date(2026, 8, 20))
    config = ClusteringConfig(min_cluster_size=5, min_samples=3)

    result_a = clustering_service.cluster(parcels_a, seed=0, config=config)
    result_b = clustering_service.cluster(parcels_b, seed=0, config=config)

    scaler_a = result_a.metadata["scaler"]
    scaler_b = result_b.metadata["scaler"]
    assert np.allclose(scaler_a.mean_, scaler_b.mean_)
    assert np.allclose(scaler_a.scale_, scaler_b.scale_)


def test_fragile_is_not_in_the_feature_vector():
    from app.services.clustering_common import raw_feature_matrix

    p1 = _make_parcel("A", 6.9, 79.8, fragile=True)
    p2 = _make_parcel("B", 6.9, 79.8, fragile=False)
    # identical in every respect except `fragile` -> identical feature rows
    X = raw_feature_matrix([p1, p2], depot_lat=6.9271, depot_lon=79.8612)
    assert np.allclose(X[0], X[1])


def test_noise_reassigned_within_radius_else_singleton():
    parcels = [_make_parcel(f"P{i}", 6.90, 79.85) for i in range(3)]
    far = _make_parcel("FAR", 6.90 + 5.0, 79.85)  # ~550km away, well beyond assign radius
    parcels.append(far)
    labels = np.array([0, 0, 0, -1])
    config = ClusteringConfig(noise_max_assign_km=3.0)

    new_labels = handle_noise(parcels, labels, config)

    assert new_labels[-1] != 0  # too far to join cluster 0 -> singleton
    assert parcels[-1].is_noise is True
    assert all(not p.is_noise for p in parcels[:-1])


def test_hdbscan_and_kmeans_share_the_same_interface(db_session):
    _tight_two_cluster_instance(db_session, n_per_cluster=15)
    parcels_h = get_planning_instance(db_session, "D1", date(2026, 8, 20))
    parcels_k = get_planning_instance(db_session, "D1", date(2026, 8, 20))

    hdb_config = ClusteringConfig(min_cluster_size=5, min_samples=3)
    kmeans_config = ClusteringConfig(mean_vehicle_capacity_m3=0.1)

    hdb_result = clustering_service.cluster(parcels_h, seed=1, config=hdb_config)
    kmeans_result = baseline_clustering.cluster(parcels_k, seed=1, config=kmeans_config)

    for result in (hdb_result, kmeans_result):
        assert hasattr(result, "labels")
        assert hasattr(result, "n_clusters")
        assert hasattr(result, "noise_count")
        assert hasattr(result, "runtime_seconds")
        assert result.n_clusters >= 1


def test_kmeans_requires_mean_vehicle_capacity_no_literal_default(db_session):
    _tight_two_cluster_instance(db_session, n_per_cluster=5)
    parcels = get_planning_instance(db_session, "D1", date(2026, 8, 20))
    with pytest.raises(ValueError):
        baseline_clustering.cluster(parcels, seed=0, config=ClusteringConfig())
