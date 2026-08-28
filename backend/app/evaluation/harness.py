"""Read-only Beanie evaluation harness.

Benchmark parcels are loaded exclusively through ``get_planning_instance``
and deep-copied. This module never inserts a plan or updates parcel state.
"""
import os
for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from app.core.reproducibility import set_seeds
from app.evaluation.synthetic_data import generate_synthetic_parcels
from app.evaluation.utilization_ceiling import compute_utilization_ceiling, compute_utilization_greedy_reference
from app.optimization.assignment_problem import AssignmentConfig, decode, load_catalog_snapshot, run_nsga2, vehicle_metrics
from app.optimization.selection import hypervolume, select_solution
from app.services import baseline_clustering, clustering_service
from app.services.capacity_aware_clustering import RepairConfig, group_by_cluster, repair_clusters
from app.services.clustering_common import ClusteringConfig, get_planning_instance
from app.services.depot_service import get_depot_or_fail
from app.services.noise_rescue import assert_complete_cluster_assignment, rescue_noise
from app.services.vehicle_catalog_service import VehicleCatalogCache, list_available_types


def _clustering_context(parcels, clustered):
    non_noise_labels = [int(label) for label in clustered.labels if int(label) >= 0]
    counts = np.asarray([
        non_noise_labels.count(label) for label in sorted(set(non_noise_labels))
    ], dtype=float)
    if not len(counts):
        return {"max_cluster_share": 0.0, "normalized_cluster_size_entropy": 0.0, "degenerate": False}
    max_share = float(counts.max() / len(parcels))
    shares = counts / counts.sum()
    entropy = float(-(shares * np.log(shares)).sum())
    normalized = entropy / np.log(len(counts)) if len(counts) > 1 else 0.0
    return {
        "max_cluster_share": max_share,
        "normalized_cluster_size_entropy": normalized,
        "degenerate": max_share > 0.60,
    }


def _prepare_warm_clusters(clusters, catalog, capacity_aware, *, depot_lat, depot_lon, seed):
    if not capacity_aware:
        status = {cid: {"feasible": True, "reason": None} for cid in clusters}
        return clusters, {"enabled": False, "n_split": 0, "n_merged": 0, "cluster_status": status, "excluded_infeasible_count": 0}
    repaired = repair_clusters(clusters, catalog, RepairConfig(), depot_lat, depot_lon, seed=seed)
    for cid, members in repaired.clusters.items():
        status = repaired.cluster_status[cid]
        for parcel in members:
            # Some unit tests use opaque sentinels to exercise audit plumbing.
            if not hasattr(parcel, "parcel_id"):
                continue
            if status["feasible"]:
                parcel.cluster_id = cid
                parcel.cluster_assignment_status = "NOISE_RESCUED" if parcel.is_noise else "NORMAL_CLUSTER"
                parcel.unassigned_reason = None
            else:
                parcel.cluster_id = -1
                parcel.cluster_assignment_status = "UNASSIGNED"
                parcel.unassigned_reason = parcel.unassigned_reason or {
                    "temporally_infeasible": "TEMPORALLY_INFEASIBLE",
                    "split_depth_cap": "SPLIT_DEPTH_CAP",
                    "no_fitting_vehicle": "NO_FITTING_VEHICLE",
                }.get(status.get("reason"), "UNKNOWN")
    feasible = {cid: rows for cid, rows in repaired.clusters.items() if repaired.cluster_status[cid]["feasible"]}
    return feasible, {
        "enabled": True, "n_split": repaired.n_split, "n_merged": repaired.n_merged,
        "clusters_before": repaired.clusters_before, "clusters_after": repaired.clusters_after,
        "cluster_status": repaired.cluster_status,
        "audit": repaired.audit,
        "excluded_infeasible_count": repaired.excluded_infeasible_count,
    }


@dataclass
class RunConfig:
    population: int = 100
    generations: int = 200
    seed: int = 0
    synthetic: bool = False
    n_parcels: int = 400
    n_clusters: int = 8
    depot_id: str = "D-CMB-001"
    delivery_date: str = "2026-01-05"


@dataclass
class PipelineRunConfig:
    depot_id: str
    delivery_date: str
    method: str
    capacity_aware: bool
    seed: int
    population: int = 100
    generations: int = 200
    feature_set: str = "location"
    time_weight: float = 5.0
    include_window_width: bool = False
    enforce_weight_order: bool = False

    @property
    def run_id(self):
        return (
            f"{self.depot_id}_{self.delivery_date}_{self.method}_"
            f"features-{self.feature_set}_tw{self.time_weight:g}_"
            f"ww{int(self.include_window_width)}_cap{int(self.capacity_aware)}_seed{self.seed}"
        )


async def evaluation_catalog_snapshot(depot_id="D-CMB-001", delivery_date=None):
    return await load_catalog_snapshot(depot_id, delivery_date)


async def run_one(cfg):
    set_seeds(cfg.seed)
    depot = await get_depot_or_fail(cfg.depot_id)
    catalog = await load_catalog_snapshot(cfg.depot_id, date.fromisoformat(cfg.delivery_date))
    parcels = generate_synthetic_parcels(cfg.n_parcels, cfg.seed, cfg.n_clusters, depot.lat, depot.lng) if cfg.synthetic else [p.model_copy(deep=True) for p in await get_planning_instance(cfg.depot_id, date.fromisoformat(cfg.delivery_date), include_carryover=False)]
    config = AssignmentConfig(depot_lat=depot.lat, depot_lon=depot.lng, population=cfg.population, generations=cfg.generations)
    started = time.perf_counter()
    problem, result = run_nsga2(parcels, catalog, config, seed=cfg.seed)
    return {"seed": cfg.seed, "elapsed_seconds": time.perf_counter() - started, "cache_hit_rate": problem.cache_hit_rate(), "short_circuit_rate": problem.short_circuit_rate(), "n_pareto_solutions": len(result.F)}


async def run_pipeline_one(cfg):
    set_seeds(cfg.seed)
    target_date = date.fromisoformat(cfg.delivery_date)
    depot = await get_depot_or_fail(cfg.depot_id)
    cache = VehicleCatalogCache()
    rows = await list_available_types(cfg.depot_id, target_date, cache=cache)
    catalog = await load_catalog_snapshot(cfg.depot_id, target_date, cache=cache)
    parcels = [p.model_copy(deep=True) for p in await get_planning_instance(cfg.depot_id, target_date, include_carryover=False)]
    mean_capacity = sum(v.capacity_m3 for v in rows) / len(rows)
    cluster_config = ClusteringConfig(
        depot_lat=depot.lat, depot_lon=depot.lng,
        feature_set=cfg.feature_set, time_weight=cfg.time_weight,
        include_window_width=cfg.include_window_width,
        mean_vehicle_capacity_m3=mean_capacity if cfg.method == "kmeans" else None,
    )
    cluster_fn = clustering_service.cluster if cfg.method == "hdbscan" else baseline_clustering.cluster
    started = time.perf_counter()
    clustered = cluster_fn(parcels, cfg.seed, cluster_config)
    noise_rescue = None
    if cfg.method == "hdbscan":
        noise_rescue = rescue_noise(parcels, catalog, cluster_config, RepairConfig())
        clustered.post_noise_cluster_count = len({p.cluster_id for p in parcels if p.cluster_id >= 0})
    warm, audit = _prepare_warm_clusters(group_by_cluster(parcels), catalog, cfg.capacity_aware, depot_lat=depot.lat, depot_lon=depot.lng, seed=cfg.seed)
    if cfg.method == "hdbscan":
        assert_complete_cluster_assignment(parcels)
    included_ids = {p.parcel_id for members in warm.values() for p in members}
    included = [p for p in parcels if p.parcel_id in included_ids]
    if not included:
        raise ValueError("All repaired clusters are infeasible; no parcels remain for NSGA-II.")
    ga_config = AssignmentConfig(depot_lat=depot.lat, depot_lon=depot.lng, population=cfg.population, generations=cfg.generations, enforce_weight_order=cfg.enforce_weight_order)
    problem, result = run_nsga2(included, catalog, ga_config, seed=cfg.seed, warm_start_clusters=warm)
    selected, front, decisions, constraints = select_solution(result)
    slots, types = decode(decisions[selected], problem.n, problem.K)
    metrics = [vehicle_metrics([included[i] for i in members], catalog[int(types[slot])], ga_config) for slot, members in slots.items() if members]
    final_g = result.pop.get("G") if result.pop is not None else np.empty((0, 0))
    selected_violation = np.maximum(constraints[selected], 0.0)
    ceiling = compute_utilization_ceiling(sum(p.weight_kg for p in included), sum(p.volume_m3 for p in included), catalog)
    greedy = compute_utilization_greedy_reference(included, catalog, enforce_weight_order=cfg.enforce_weight_order)
    mean_util = sum(m["utilization"] for m in metrics) / len(metrics)
    total_fleet_cost = sum(m["cost"] for m in metrics)
    clustering_context = _clustering_context(parcels, clustered)
    temporal_split_count = sum(
        bool(row.get("temporal_split_predicate_fired"))
        for row in audit.get("audit", [])
    )
    return {
        "run_id": cfg.run_id, "depot_id": cfg.depot_id, "delivery_date": cfg.delivery_date,
        "method": cfg.method, "capacity_aware": cfg.capacity_aware, "seed": cfg.seed,
        "feature_set": cfg.feature_set, "time_weight": cfg.time_weight,
        "include_window_width": cfg.include_window_width,
        "n_parcels": len(included), "excluded_parcels": len(parcels) - len(included),
        "raw_cluster_count": clustered.n_clusters, "post_noise_cluster_count": clustered.post_noise_cluster_count,
        "noise_count": clustered.noise_count,
        "noise_fraction": clustered.noise_count / len(parcels),
        **({f"noise_rescue_{key}": value for key, value in noise_rescue.summary().items()}
           if noise_rescue is not None else {
               "noise_rescue_joined_existing_count": 0,
               "noise_rescue_rescue_group_count": 0,
               "noise_rescue_rescue_group_parcel_count": 0,
               "noise_rescue_singleton_count": 0,
               "noise_rescue_unresolved_count": 0,
           }),
        **clustering_context,
        "mean_utilization": mean_util,
        "cost_per_parcel": total_fleet_cost / len(included),
        "mean_weight_utilization": sum(m["util_weight"] for m in metrics) / len(metrics),
        "mean_volume_utilization": sum(m["util_volume"] for m in metrics) / len(metrics),
        "utilization_ceiling_capacity": ceiling.utilization, "utilization_greedy_reference": greedy.utilization,
        "achieved_vs_greedy_reference": mean_util / greedy.utilization if greedy.utilization else 0.0,
        "total_distance_km": sum(m["distance"] for m in metrics),
        "mean_time_window_compliance": sum(m["compliance"] for m in metrics) / len(metrics),
        "total_fleet_cost": total_fleet_cost, "n_vehicles": len(metrics),
        "hypervolume": hypervolume(front), "pareto_front_size": len(front),
        "feasible": bool(np.all(selected_violation <= 1e-12)),
        "feasible_individuals_final": int(np.sum(np.all(final_g <= 1e-12, axis=1))) if len(final_g) else 0,
        "max_constraint_violation": float(np.max(selected_violation, initial=0.0)),
        "temporal_split_predicate_count": temporal_split_count,
        "runtime_seconds": time.perf_counter() - started, "repair_audit": audit,
    }


async def run_pipeline_batch_async(configs, *, n_jobs=1, out_dir):
    """Stage 1 uses serial execution; process parallelism is added in Stage 4."""
    if n_jobs != 1:
        raise ValueError("Parallel evaluation is not enabled until the Stage 4 determinism gate passes.")
    path = Path(out_dir); path.mkdir(parents=True, exist_ok=True)
    output = []
    for cfg in configs:
        target = path / f"{cfg.run_id}.json"
        row = json.loads(target.read_text()) if target.exists() else await run_pipeline_one(cfg)
        if not target.exists(): target.write_text(json.dumps(row, indent=2, default=str))
        output.append(row)
    return output


def run_pipeline_batch(configs, *, n_jobs=1, out_dir):
    return asyncio.run(run_pipeline_batch_async(configs, n_jobs=n_jobs, out_dir=out_dir))
