"""Phase 2 gate: after repair_clusters, every cluster fits at least one
vehicle type, no parcel is lost or duplicated, and split/merge/peel counts
in the audit trail are internally consistent."""
from dataclasses import dataclass

import pytest

from app.models.parcel import Parcel
from app.services.capacity_aware_clustering import (
    RepairConfig,
    _fits_some_vehicle,
    group_by_cluster,
    repair_clusters,
)


@dataclass
class FakeVehicleType:
    code: str
    capacity_kg: float
    capacity_m3: float
    cargo_length_cm: float
    cargo_width_cm: float
    cargo_height_cm: float


SMALL_VAN = FakeVehicleType("SMALL", 100.0, 1.0, 150.0, 100.0, 100.0)
LARGE_LORRY = FakeVehicleType("LARGE", 5000.0, 25.0, 550.0, 220.0, 220.0)
CATALOG = [SMALL_VAN, LARGE_LORRY]


def _parcel(pid, cluster_id, weight=2.0, volume=0.01, lat=6.90, lon=79.85, **overrides):
    defaults = dict(
        parcel_id=pid,
        depot_id="D1",
        cluster_id=cluster_id,
        weight_kg=weight,
        volume_m3=volume,
        latitude=lat,
        longitude=lon,
        time_window_start="10:00",
        time_window_end="13:00",
        length_cm=20,
        width_cm=20,
        height_cm=20,
        hazardous=False,
        requires_refrigeration=False,
        hazmat_class=None,
    )
    defaults.update(overrides)
    return Parcel(**defaults)


def test_oversize_cluster_is_split_until_it_fits():
    # 80 parcels x 2kg = 160kg > SMALL_VAN.capacity_kg (100kg); spatially
    # spread so 2-means can actually separate them, forced to split by
    # using a catalog with only SMALL_VAN available.
    parcels = [
        _parcel(f"P{i}", cluster_id=0, weight=2.0, lat=6.90 + 0.001 * i, lon=79.85 + 0.001 * i)
        for i in range(80)
    ]
    clusters = group_by_cluster(parcels)

    repaired = repair_clusters(clusters, [SMALL_VAN], RepairConfig(), depot_lat=6.9271, depot_lon=79.8612)

    for cid, members in repaired.clusters.items():
        assert _fits_some_vehicle(members, [SMALL_VAN]), f"cluster {cid} does not fit any vehicle"
    assert repaired.n_split > 0
    assert repaired.clusters_after > repaired.clusters_before


def test_no_parcel_lost_or_duplicated_through_split_and_merge():
    parcels = [_parcel(f"P{i}", cluster_id=i % 5, weight=1.0, volume=0.005) for i in range(40)]
    clusters = group_by_cluster(parcels)
    original_ids = {p.parcel_id for p in parcels}

    repaired = repair_clusters(clusters, CATALOG, RepairConfig(), depot_lat=6.9271, depot_lon=79.8612)

    result_ids = [p.parcel_id for members in repaired.clusters.values() for p in members]
    assert sorted(result_ids) == sorted(original_ids)
    assert len(result_ids) == len(set(result_ids))


def test_hazardous_parcels_are_peeled_into_their_own_cluster():
    normal = [_parcel(f"N{i}", cluster_id=0) for i in range(5)]
    hazmat = [_parcel(f"H{i}", cluster_id=0, hazardous=True, hazmat_class="FLAMMABLE") for i in range(3)]
    clusters = group_by_cluster(normal + hazmat)

    repaired = repair_clusters(clusters, CATALOG, RepairConfig(), depot_lat=6.9271, depot_lon=79.8612)

    assert repaired.n_peeled == 3
    peeled_clusters = [
        members for members in repaired.clusters.values()
        if all(p.hazardous for p in members) and members
    ]
    assert any(len(c) == 3 for c in peeled_clusters)
    # no cluster should now mix hazardous and non-hazardous parcels
    for members in repaired.clusters.values():
        hazardous_flags = {p.hazardous for p in members}
        assert len(hazardous_flags) <= 1


def test_undersize_clusters_within_range_are_merged():
    # two tiny, nearby, time-compatible clusters that together still fit SMALL_VAN
    cluster_a = [_parcel("A1", cluster_id=0, weight=1.0, lat=6.9000, lon=79.8500)]
    cluster_b = [_parcel("B1", cluster_id=1, weight=1.0, lat=6.9005, lon=79.8505)]
    clusters = group_by_cluster(cluster_a + cluster_b)

    repaired = repair_clusters(
        clusters, [SMALL_VAN], RepairConfig(merge_max_centroid_km=5.0), depot_lat=6.9271, depot_lon=79.8612
    )

    assert repaired.n_merged == 1
    assert repaired.clusters_after == 1


def test_far_apart_undersize_clusters_are_not_merged():
    cluster_a = [_parcel("A1", cluster_id=0, weight=1.0, lat=6.90, lon=79.85)]
    cluster_b = [_parcel("B1", cluster_id=1, weight=1.0, lat=7.05, lon=80.00)]  # far away
    clusters = group_by_cluster(cluster_a + cluster_b)

    repaired = repair_clusters(
        clusters, [SMALL_VAN], RepairConfig(merge_max_centroid_km=2.0), depot_lat=6.9271, depot_lon=79.8612
    )

    assert repaired.n_merged == 0
    assert repaired.clusters_after == 2


def test_no_catalog_no_cluster_can_fit_anything():
    assert _fits_some_vehicle([_parcel("A", cluster_id=0)], []) is False


def test_recursion_depth_cap_is_recorded_when_hit():
    # 8 spatially distinct, very heavy parcels: 2-means can keep bisecting
    # them, but even a pair (2000kg) is still far over SMALL_VAN's 100kg, so
    # splitting must hit the depth cap before ever reaching a fit.
    parcels = [
        _parcel(f"P{i}", cluster_id=0, weight=1000.0, lat=6.90 + 0.01 * i, lon=79.85 + 0.01 * i)
        for i in range(8)
    ]
    clusters = group_by_cluster(parcels)

    repaired = repair_clusters(
        clusters, [SMALL_VAN], RepairConfig(max_split_recursion_depth=2), depot_lat=6.9271, depot_lon=79.8612
    )

    assert repaired.max_depth_hit is True
    total = sum(len(m) for m in repaired.clusters.values())
    assert total == 8
