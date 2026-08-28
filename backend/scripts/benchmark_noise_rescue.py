"""Reproducible 400-parcel noise-rescue benchmark (seed 0)."""
from copy import deepcopy
from datetime import date
import json
from statistics import median
import time

from app.db.seed_vehicle_types import FIELD_DATA_VEHICLE_TYPES
from app.evaluation.clustering_feature_experiment import load_instances
from app.services.capacity_aware_clustering import RepairConfig, group_by_cluster, repair_clusters
from app.services.clustering_common import ClusteringConfig
from app.services.clustering_service import cluster
from app.services.noise_rescue import assert_complete_cluster_assignment, rescue_noise


def measure(source, rescue):
    parcels = deepcopy(source)
    config = ClusteringConfig(depot_lat=6.9271, depot_lon=79.8612)
    started = time.perf_counter()
    clustered = cluster(parcels, 0, config)
    rescue_result = rescue_noise(parcels, FIELD_DATA_VEHICLE_TYPES, config, RepairConfig()) if rescue else None
    repaired = repair_clusters(
        group_by_cluster(parcels), FIELD_DATA_VEHICLE_TYPES, RepairConfig(),
        config.depot_lat, config.depot_lon, seed=0,
    )
    positive = {cid: members for cid, members in repaired.clusters.items()
                if repaired.cluster_status[cid]["feasible"]}
    unresolved_ids = {p.parcel_id for p in parcels if p.cluster_id == -1}
    unresolved_ids.update(
        p.parcel_id for cid, members in repaired.clusters.items()
        if not repaired.cluster_status[cid]["feasible"] for p in members
    )
    unresolved = len(unresolved_ids)
    if rescue:
        # Repair is read/write on cluster ids but its return object is the
        # authoritative final partition for this diagnostic.
        for cid, members in repaired.clusters.items():
            for parcel in members:
                if repaired.cluster_status[cid]["feasible"]:
                    parcel.cluster_id = cid
                    parcel.unassigned_reason = None
                else:
                    parcel.cluster_id = -1
                    parcel.unassigned_reason = parcel.unassigned_reason or "REPAIR_INFEASIBLE"
        assert_complete_cluster_assignment(parcels)
    return {
        "raw_clusters": clustered.n_clusters,
        "original_noise": clustered.noise_count,
        "positive_clusters_post_repair": len(positive),
        "unassigned_post_repair": unresolved,
        "noise_rescue": rescue_result.summary() if rescue_result else None,
        "runtime_seconds": time.perf_counter() - started,
    }


if __name__ == "__main__":
    source = load_instances()[("D-CMB-001", date(2026, 1, 5))]
    measure(source, False); measure(source, True)  # warm imports/caches
    before = [measure(source, False) for _ in range(5)]
    after = [measure(source, True) for _ in range(5)]
    output = {"without_rescue": before[-1], "with_rescue": after[-1]}
    output["without_rescue"]["runtime_seconds_median_5"] = median(r["runtime_seconds"] for r in before)
    output["with_rescue"]["runtime_seconds_median_5"] = median(r["runtime_seconds"] for r in after)
    print(json.dumps(output, indent=2))
