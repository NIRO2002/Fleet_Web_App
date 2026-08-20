"""Phase 2 gate: after repair_clusters, every cluster fits at least one
vehicle type, no parcel is lost or duplicated, and split/merge counts in
the audit trail are internally consistent. Fix Pass 3 G1 dropped the
"peel" operation (hazmat/refrigeration are out of scope for commercial
last-mile delivery); this is split-and-merge only now."""
from dataclasses import dataclass, replace

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
    max_parcels: int = 500
    max_stack_layers: int = 6
    vehicle_max_stack_weight_kg: float = 10_000.0
    has_tail_lift: bool = True


SMALL_VAN = FakeVehicleType("SMALL", 100.0, 1.0, 150.0, 100.0, 100.0)
LARGE_LORRY = FakeVehicleType("LARGE", 5000.0, 25.0, 550.0, 220.0, 220.0)
CATALOG = [SMALL_VAN, LARGE_LORRY]


def test_aggregate_fit_but_placement_infeasible_cluster_is_split():
    one_layer_van = replace(SMALL_VAN, max_stack_layers=1)
    parcels = [
        _parcel(f"PLACE-{i}", cluster_id=0, weight=1.0, volume=0.004, lat=6.90 + i * 0.0001)
        for i in range(50)
    ]

    repaired = repair_clusters(group_by_cluster(parcels), [one_layer_van], RepairConfig())

    assert repaired.n_split > 0
    assert all(_fits_some_vehicle(members, [one_layer_van]) for members in repaired.clusters.values())
    checks = [row for row in repaired.audit if row["operation"] == "split_check"]
    assert checks
    assert {"total_weight_kg", "total_volume_m3", "longest_parcel_dimension_cm"} <= checks[0].keys()


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


def test_splitter_threads_run_seed_to_kmeans(monkeypatch):
    import app.services.capacity_aware_clustering as module

    observed = []
    original = module.KMeans

    def capture(*args, **kwargs):
        observed.append(kwargs.get("random_state"))
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "KMeans", capture)
    parcels = [
        _parcel(f"SEED-{i}", cluster_id=0, weight=2.0, lat=6.90 + 0.001 * i, lon=79.85 + 0.001 * i)
        for i in range(80)
    ]
    repair_clusters(group_by_cluster(parcels), [SMALL_VAN], seed=37)
    assert observed and set(observed) == {37}


def test_no_parcel_lost_or_duplicated_through_split_and_merge():
    parcels = [_parcel(f"P{i}", cluster_id=i % 5, weight=1.0, volume=0.005) for i in range(40)]
    clusters = group_by_cluster(parcels)
    original_ids = {p.parcel_id for p in parcels}

    repaired = repair_clusters(clusters, CATALOG, RepairConfig(), depot_lat=6.9271, depot_lon=79.8612)

    result_ids = [p.parcel_id for members in repaired.clusters.values() for p in members]
    assert sorted(result_ids) == sorted(original_ids)
    assert len(result_ids) == len(set(result_ids))


def test_merge_never_combines_clusters_with_different_handling_classes():
    """Without peel (dropped in Fix Pass 3 G1), a cluster coming out of
    spatial clustering can already contain a mix of hazardous/ordinary
    parcels -- `_cluster_handling_key` must compare the *exact set* of
    handling classes present, not assume homogeneity, so merge never
    combines two clusters whose handling-class mix differs."""
    # cluster A: one hazardous + one ordinary parcel (mixed set); very close
    # to cluster B, which is purely ordinary -- must NOT merge, since their
    # handling-class sets differ ({None, "HAZMAT:..."} vs {None}).
    mixed = [
        _parcel("A-HAZ", cluster_id=0, lat=6.9000, lon=79.8500, hazardous=True, hazmat_class="FLAMMABLE"),
        _parcel("A-ORD", cluster_id=0, lat=6.9000, lon=79.8500),
    ]
    ordinary = [_parcel("B-ORD", cluster_id=1, lat=6.9001, lon=79.8501)]
    clusters = group_by_cluster(mixed + ordinary)

    repaired = repair_clusters(
        clusters, [SMALL_VAN], RepairConfig(merge_max_centroid_km=5.0), depot_lat=6.9271, depot_lon=79.8612
    )

    assert repaired.n_merged == 0
    assert repaired.clusters_after == 2

    # two clusters with the *same* mixed composition may still merge.
    mixed_a = [
        _parcel("C-HAZ", cluster_id=2, lat=6.9100, lon=79.8600, hazardous=True, hazmat_class="FLAMMABLE"),
        _parcel("C-ORD", cluster_id=2, lat=6.9100, lon=79.8600),
    ]
    mixed_b = [
        _parcel("D-HAZ", cluster_id=3, lat=6.9101, lon=79.8601, hazardous=True, hazmat_class="FLAMMABLE"),
        _parcel("D-ORD", cluster_id=3, lat=6.9101, lon=79.8601),
    ]
    matching_clusters = group_by_cluster(mixed_a + mixed_b)

    repaired_matching = repair_clusters(
        matching_clusters, [SMALL_VAN], RepairConfig(merge_max_centroid_km=5.0),
        depot_lat=6.9271, depot_lon=79.8612,
    )
    assert repaired_matching.n_merged == 1


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
