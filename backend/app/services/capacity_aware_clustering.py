"""Capacity-aware cluster repair.

This is the research novelty the dissertation's central claim rests on
(spatial clustering + capacity-aware repair + NSGA-II beats a naive
baseline) and it did not exist before this remediation. It runs between
clustering (HDBSCAN or K-Means) and NSGA-II assignment (Phase 3), and is
independently switchable (`capacity_aware=False` in the pipeline, Phase 4)
so its marginal contribution can be ablated in the evaluation harness
(Phase 5).

Two operations, applied in this order: recursively split clusters that
don't fit any catalog vehicle, then greedily merge clusters that are small
enough to share one vehicle and close enough in space and time. This is
split-and-merge, not split-merge-peel — a third "peel" operation (grouping
hazmat/refrigerated parcels into their own clusters before splitting) was
dropped in Fix Pass 3 G1 when hazmat/refrigeration vehicle-eligibility
constraints were descoped from NSGA-II (out of scope for commercial
last-mile delivery; see docs/DESIGN_DECISIONS.md). Merge still keeps
clusters with different handling classes apart (`_cluster_handling_key`)
purely because merging, say, a hazardous cluster into a non-hazardous one
would misrepresent the resulting cluster's contents — an independent reason
that doesn't depend on peel existing.
"""
from dataclasses import dataclass, field

import numpy as np
from sklearn.cluster import KMeans

from app.core.config import settings
from app.models.parcel import Parcel
from app.services.clustering_common import project_to_metric
from app.utils_time import minutes


@dataclass
class RepairConfig:
    merge_max_centroid_km: float = 2.0
    max_split_recursion_depth: int = 6


@dataclass
class RepairedClusters:
    clusters: dict[int, list[Parcel]]
    n_split: int = 0
    n_merged: int = 0
    clusters_before: int = 0
    clusters_after: int = 0
    max_depth_hit: bool = False
    audit: list[dict] = field(default_factory=list)


def group_by_cluster(parcels: list[Parcel]) -> dict[int, list[Parcel]]:
    groups: dict[int, list[Parcel]] = {}
    for parcel in parcels:
        groups.setdefault(parcel.cluster_id, []).append(parcel)
    return groups


def _fits_some_vehicle(parcels: list[Parcel], vehicle_catalog) -> bool:
    if not vehicle_catalog:
        return False
    total_weight = sum(p.weight_kg for p in parcels)
    total_volume = sum(p.volume_m3 for p in parcels)
    longest_side = max(
        (max(p.length_cm or 0.0, p.width_cm or 0.0, p.height_cm or 0.0) for p in parcels),
        default=0.0,
    )
    for vehicle in vehicle_catalog:
        if total_weight > vehicle.capacity_kg or total_volume > vehicle.capacity_m3:
            continue
        cargo_longest = max(vehicle.cargo_length_cm, vehicle.cargo_width_cm, vehicle.cargo_height_cm)
        if longest_side > cargo_longest:
            continue
        return True
    return False


def _handling_key(parcel: Parcel) -> str | None:
    if parcel.hazardous or parcel.hazmat_class:
        return f"HAZMAT:{parcel.hazmat_class or 'GENERAL'}"
    if parcel.requires_refrigeration:
        return "REFRIGERATED"
    return None


def _cluster_handling_key(parcels: list[Parcel]) -> frozenset:
    """The exact set of handling classes present in a cluster (including
    `None` for ordinary parcels, as a member of the set). Without peel
    upstream (dropped in Fix Pass 3 G1), a cluster coming out of spatial
    clustering or a geographic split can legitimately contain a mix of
    hazmat/refrigerated/ordinary parcels -- so this can no longer assume
    homogeneity and take a single representative key. Merge only combines
    two clusters whose handling-class sets match *exactly*, so a merge can
    never introduce a handling class that wasn't already present in both
    sides."""
    return frozenset(_handling_key(p) for p in parcels)


def _split_oversize(
    clusters: dict[int, list[Parcel]],
    vehicle_catalog,
    config: RepairConfig,
    depot_lat: float,
    depot_lon: float,
    next_id: int,
    audit: list[dict],
):
    n_split = 0
    max_depth_hit = False
    queue = [(cid, parcels, 0) for cid, parcels in clusters.items()]
    result: dict[int, list[Parcel]] = {}

    while queue:
        cluster_id, parcels, depth = queue.pop(0)
        if len(parcels) <= 1 or _fits_some_vehicle(parcels, vehicle_catalog):
            result[cluster_id] = parcels
            continue
        if depth >= config.max_split_recursion_depth:
            max_depth_hit = True
            result[cluster_id] = parcels
            audit.append(
                {"operation": "split_depth_cap", "cluster_id": cluster_id, "parcel_count": len(parcels), "depth": depth}
            )
            continue

        coords = project_to_metric(parcels, depot_lat, depot_lon)
        sub_labels = KMeans(n_clusters=2, random_state=0, n_init=10).fit_predict(coords)
        group_a = [p for p, lbl in zip(parcels, sub_labels) if lbl == 0]
        group_b = [p for p, lbl in zip(parcels, sub_labels) if lbl == 1]
        if not group_a or not group_b:
            result[cluster_id] = parcels
            continue

        n_split += 1
        audit.append(
            {
                "operation": "split",
                "cluster_id": cluster_id,
                "into": [next_id, next_id + 1],
                "sizes": [len(group_a), len(group_b)],
            }
        )
        queue.append((next_id, group_a, depth + 1))
        queue.append((next_id + 1, group_b, depth + 1))
        next_id += 2

    return result, next_id, n_split, max_depth_hit


def _cluster_window_minutes(parcels: list[Parcel]) -> tuple[int, int]:
    starts = [minutes(p.time_window_start) for p in parcels]
    ends = [minutes(p.time_window_end) for p in parcels]
    return min(starts), max(ends)


def _overlap_minutes(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def _merge_undersize(
    clusters: dict[int, list[Parcel]],
    vehicle_catalog,
    config: RepairConfig,
    depot_lat: float,
    depot_lon: float,
    audit: list[dict],
):
    n_merged = 0
    cluster_ids = list(clusters.keys())

    while True:
        best_pair = None
        best_distance = float("inf")
        for i in range(len(cluster_ids)):
            for j in range(i + 1, len(cluster_ids)):
                cid_a, cid_b = cluster_ids[i], cluster_ids[j]
                if cid_a not in clusters or cid_b not in clusters:
                    continue
                parcels_a, parcels_b = clusters[cid_a], clusters[cid_b]
                if _cluster_handling_key(parcels_a) != _cluster_handling_key(parcels_b):
                    continue
                if not _fits_some_vehicle(parcels_a + parcels_b, vehicle_catalog):
                    continue

                centroid_a = project_to_metric(parcels_a, depot_lat, depot_lon).mean(axis=0)
                centroid_b = project_to_metric(parcels_b, depot_lat, depot_lon).mean(axis=0)
                distance = float(np.linalg.norm(centroid_a - centroid_b))
                if distance > config.merge_max_centroid_km:
                    continue

                start_a, end_a = _cluster_window_minutes(parcels_a)
                start_b, end_b = _cluster_window_minutes(parcels_b)
                if _overlap_minutes(start_a, end_a, start_b, end_b) <= 0:
                    continue

                if distance < best_distance:
                    best_distance = distance
                    best_pair = (cid_a, cid_b)

        if best_pair is None:
            break

        cid_a, cid_b = best_pair
        clusters[cid_a] = clusters[cid_a] + clusters[cid_b]
        del clusters[cid_b]
        cluster_ids = [cid for cid in cluster_ids if cid != cid_b]
        n_merged += 1
        audit.append({"operation": "merge", "into": cid_a, "absorbed": cid_b, "centroid_distance_km": best_distance})

    return clusters, n_merged


def repair_clusters(
    parcels_by_cluster: dict[int, list[Parcel]],
    vehicle_catalog,
    config: RepairConfig | None = None,
    depot_lat: float = settings.depot_latitude,
    depot_lon: float = settings.depot_longitude,
) -> RepairedClusters:
    config = config or RepairConfig()
    clusters = {cid: list(parcels) for cid, parcels in parcels_by_cluster.items()}
    clusters_before = len(clusters)
    total_before = sum(len(p) for p in clusters.values())

    audit: list[dict] = []
    next_id = (max(clusters.keys()) + 1) if clusters else 0

    clusters, next_id, n_split, max_depth_hit = _split_oversize(
        clusters, vehicle_catalog, config, depot_lat, depot_lon, next_id, audit
    )
    clusters, n_merged = _merge_undersize(clusters, vehicle_catalog, config, depot_lat, depot_lon, audit)

    total_after = sum(len(p) for p in clusters.values())
    if total_after != total_before:
        raise AssertionError(
            f"capacity-aware repair lost or duplicated parcels: {total_before} -> {total_after}"
        )

    return RepairedClusters(
        clusters=clusters,
        n_split=n_split,
        n_merged=n_merged,
        clusters_before=clusters_before,
        clusters_after=len(clusters),
        max_depth_hit=max_depth_hit,
        audit=audit,
    )
