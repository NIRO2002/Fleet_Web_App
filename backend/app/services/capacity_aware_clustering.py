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
split-and-merge, not split-merge-peel - a third "peel" operation (grouping
hazmat/refrigerated parcels into their own clusters before splitting) was
dropped in Fix Pass 3 G1 when hazmat/refrigeration vehicle-eligibility
constraints were descoped from NSGA-II (out of scope for commercial
last-mile delivery; see docs/DESIGN_DECISIONS.md). Merge still keeps
clusters with different handling classes apart (`_cluster_handling_key`)
purely because merging, say, a hazardous cluster into a non-hazardous one
would misrepresent the resulting cluster's contents - an independent reason
that doesn't depend on peel existing.
"""
from dataclasses import dataclass, field, replace
import heapq

import numpy as np
from sklearn.cluster import KMeans

from app.core.config import settings
from app.models.parcel import Parcel
from app.optimization.placement import attempt_placement
from app.services.clustering_common import project_to_metric
from app.utils_time import minutes


@dataclass
class RepairConfig:
    merge_max_centroid_km: float = 2.0
    # A balanced split of a 400-parcel instance can require nine levels in
    # the worst case. Ten preserves a safety bound without prematurely
    # returning a cluster that the placement-aware predicate just rejected.
    max_split_recursion_depth: int = 10
    enforce_temporal_feasibility: bool = True
    service_time_minutes: float = 4.0


@dataclass
class RepairedClusters:
    clusters: dict[int, list[Parcel]]
    n_split: int = 0
    n_merged: int = 0
    clusters_before: int = 0
    clusters_after: int = 0
    max_depth_hit: bool = False
    audit: list[dict] = field(default_factory=list)
    cluster_status: dict[int, dict] = field(default_factory=dict)
    excluded_infeasible_count: int = 0


def group_by_cluster(parcels: list[Parcel]) -> dict[int, list[Parcel]]:
    groups: dict[int, list[Parcel]] = {}
    next_noise_id = -1
    for parcel in parcels:
        cluster_id = parcel.cluster_id
        if cluster_id == -1:
            # Noise points remain individually identifiable until repair;
            # negative IDs mark them as mergeable noise-origin singletons.
            cluster_id = next_noise_id
            next_noise_id -= 1
        groups.setdefault(cluster_id, []).append(parcel)
    return groups


def _fits_some_vehicle(
    parcels: list[Parcel], vehicle_catalog, config: RepairConfig | None = None,
    depot_lat: float = settings.depot_latitude, depot_lon: float = settings.depot_longitude,
) -> bool:
    config = config or RepairConfig()
    if not vehicle_catalog:
        return False
    total_weight = sum(p.weight_kg for p in parcels)
    total_volume = sum(p.volume_m3 for p in parcels)
    longest_side = max(
        (max(p.length_cm or 0.0, p.width_cm or 0.0, p.height_cm or 0.0) for p in parcels),
        default=0.0,
    )
    temporal_diameter_km = 0.0
    reachable_span = 0
    if config.enforce_temporal_feasibility and len(parcels) > 1:
        starts = [minutes(p.time_window_start) for p in parcels]
        ends = [minutes(p.time_window_end) for p in parcels]
        reachable_span = max(ends) - min(starts)
        coords = project_to_metric(parcels, depot_lat, depot_lon)
        # Two-sweep farthest-point lower bound: O(n), deterministic, and
        # deliberately cheaper than the former O(n^2) distance matrix.
        first = int(np.argmax(np.linalg.norm(coords - coords[0], axis=1)))
        temporal_diameter_km = float(np.max(np.linalg.norm(coords - coords[first], axis=1)))
    for vehicle in vehicle_catalog:
        if total_weight > vehicle.capacity_kg or total_volume > vehicle.capacity_m3:
            continue
        if vehicle.max_parcels is not None and len(parcels) > vehicle.max_parcels:
            continue
        cargo_longest = max(vehicle.cargo_length_cm, vehicle.cargo_width_cm, vehicle.cargo_height_cm)
        if longest_side > cargo_longest:
            continue
        if config.enforce_temporal_feasibility and len(parcels) > 1:
            lower_bound_minutes = (
                len(parcels) * config.service_time_minutes
                + temporal_diameter_km / max(vehicle.avg_speed_kmh, 1e-6) * 60.0
            )
            if lower_bound_minutes > reachable_span:
                continue
        if attempt_placement(parcels, vehicle, collect_exceptions=False) is not None:
            return True
    return False


def _split_decision_inputs(parcels, vehicle_catalog) -> dict:
    largest = max(vehicle_catalog, key=lambda v: (v.capacity_kg, v.capacity_m3))
    return {
        "parcel_count": len(parcels),
        "total_weight_kg": sum(p.weight_kg for p in parcels),
        "total_volume_m3": sum(p.volume_m3 for p in parcels),
        "longest_parcel_dimension_cm": max(
            (max(p.length_cm or 0.0, p.width_cm or 0.0, p.height_cm or 0.0) for p in parcels), default=0.0
        ),
        "largest_vehicle_code": largest.code,
        "largest_capacity_kg": largest.capacity_kg,
        "largest_capacity_m3": largest.capacity_m3,
        "largest_max_parcels": largest.max_parcels,
        "largest_cargo_dimension_cm": max(
            largest.cargo_length_cm, largest.cargo_width_cm, largest.cargo_height_cm
        ),
    }


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
    seed: int,
):
    n_split = 0
    max_depth_hit = False
    queue = [(cid, parcels, 0) for cid, parcels in clusters.items()]
    result: dict[int, list[Parcel]] = {}

    while queue:
        cluster_id, parcels, depth = queue.pop(0)
        fits = len(parcels) <= 1 or _fits_some_vehicle(parcels, vehicle_catalog, config, depot_lat, depot_lon)
        audit.append({
            "operation": "split_check",
            "cluster_id": cluster_id,
            "depth": depth,
            "fits_some_vehicle": fits,
            **_split_decision_inputs(parcels, vehicle_catalog),
        })
        if fits:
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
        sub_labels = KMeans(n_clusters=2, random_state=seed, n_init=10).fit_predict(coords)
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
    versions = {cid: 0 for cid in clusters}
    centroids = {cid: project_to_metric(rows, depot_lat, depot_lon).mean(axis=0) for cid, rows in clusters.items()}
    feasibility_cache: dict[tuple[int, int, int, int], bool] = {}
    candidates: list[tuple[float, int, int, int, int]] = []

    def add_candidate(cid_a: int, cid_b: int) -> None:
        if cid_a == cid_b or cid_a not in clusters or cid_b not in clusters:
            return
        cid_a, cid_b = sorted((cid_a, cid_b))
        parcels_a, parcels_b = clusters[cid_a], clusters[cid_b]
        if _cluster_handling_key(parcels_a) != _cluster_handling_key(parcels_b):
            return
        distance = float(np.linalg.norm(centroids[cid_a] - centroids[cid_b]))
        if distance > config.merge_max_centroid_km:
            return
        start_a, end_a = _cluster_window_minutes(parcels_a)
        start_b, end_b = _cluster_window_minutes(parcels_b)
        if _overlap_minutes(start_a, end_a, start_b, end_b) <= 0:
            return
        key = (cid_a, versions[cid_a], cid_b, versions[cid_b])
        feasible = feasibility_cache.get(key)
        if feasible is None:
            feasible = _fits_some_vehicle(parcels_a + parcels_b, vehicle_catalog, config, depot_lat, depot_lon)
            feasibility_cache[key] = feasible
        if feasible:
            heapq.heappush(candidates, (distance, cid_a, cid_b, versions[cid_a], versions[cid_b]))

    ids = sorted(clusters)
    for i, cid_a in enumerate(ids):
        for cid_b in ids[i + 1:]:
            add_candidate(cid_a, cid_b)

    while candidates:
        best_distance, cid_a, cid_b, version_a, version_b = heapq.heappop(candidates)
        if cid_a not in clusters or cid_b not in clusters:
            continue
        if versions[cid_a] != version_a or versions[cid_b] != version_b:
            continue
        clusters[cid_a] = clusters[cid_a] + clusters[cid_b]
        del clusters[cid_b]
        versions[cid_a] += 1
        versions.pop(cid_b)
        centroids[cid_a] = project_to_metric(clusters[cid_a], depot_lat, depot_lon).mean(axis=0)
        centroids.pop(cid_b)
        n_merged += 1
        audit.append({"operation": "merge", "into": cid_a, "absorbed": cid_b, "centroid_distance_km": best_distance})
        for other in sorted(clusters):
            if other != cid_a:
                add_candidate(cid_a, other)

    return clusters, n_merged


def repair_clusters(
    parcels_by_cluster: dict[int, list[Parcel]],
    vehicle_catalog,
    config: RepairConfig | None = None,
    depot_lat: float = settings.depot_latitude,
    depot_lon: float = settings.depot_longitude,
    seed: int = 0,
) -> RepairedClusters:
    config = config or RepairConfig()
    if not vehicle_catalog:
        raise ValueError("capacity-aware repair requires a non-empty vehicle catalog")
    clusters = {cid: list(parcels) for cid, parcels in parcels_by_cluster.items()}
    clusters_before = len(clusters)
    total_before = sum(len(p) for p in clusters.values())

    audit: list[dict] = []
    next_id = (max(clusters.keys()) + 1) if clusters else 0

    clusters, next_id, n_split, max_depth_hit = _split_oversize(
        clusters, vehicle_catalog, config, depot_lat, depot_lon, next_id, audit, seed
    )
    clusters, n_merged = _merge_undersize(clusters, vehicle_catalog, config, depot_lat, depot_lon, audit)

    total_after = sum(len(p) for p in clusters.values())
    if total_after != total_before:
        raise AssertionError(
            f"capacity-aware repair lost or duplicated parcels: {total_before} -> {total_after}"
        )

    depth_cap_ids = {row["cluster_id"] for row in audit if row.get("operation") == "split_depth_cap"}
    status_by_old_id = {}
    no_temporal = replace(config, enforce_temporal_feasibility=False)
    for cluster_id, members in clusters.items():
        feasible = _fits_some_vehicle(members, vehicle_catalog, config, depot_lat, depot_lon)
        reason = None
        if not feasible:
            if cluster_id in depth_cap_ids:
                reason = "split_depth_cap"
            elif _fits_some_vehicle(members, vehicle_catalog, no_temporal, depot_lat, depot_lon):
                reason = "temporally_infeasible"
            else:
                reason = "no_fitting_vehicle"
        status_by_old_id[cluster_id] = {"feasible": feasible, "reason": reason}

    normalized_clusters = {}
    normalized_status = {}
    for normalized_id, old_id in enumerate(sorted(clusters)):
        normalized_clusters[normalized_id] = clusters[old_id]
        normalized_status[normalized_id] = status_by_old_id[old_id]
        for parcel in clusters[old_id]:
            parcel.cluster_id = normalized_id

    return RepairedClusters(
        clusters=normalized_clusters,
        n_split=n_split,
        n_merged=n_merged,
        clusters_before=clusters_before,
        clusters_after=len(clusters),
        max_depth_hit=max_depth_hit,
        audit=audit,
        cluster_status=normalized_status,
        excluded_infeasible_count=sum(not row["feasible"] for row in normalized_status.values()),
    )
