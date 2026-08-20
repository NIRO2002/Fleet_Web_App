"""Fix Pass 2 item B / Fix Pass 4 items S5-S7: the evaluation harness.

Two layers:
- `RunConfig`/`run_one`/`run_batch` -- the GA-only benchmark (catalog load +
  `run_nsga2`, no persistence) used to measure raw NSGA-II runtime
  (Fix Pass 2/3/4 item B/G5/S6). Real data by default as of Fix Pass 4 S5;
  pass `synthetic=True` to fall back to `synthetic_data.py`.
- `PipelineRunConfig`/`run_pipeline_one`/`run_pipeline_batch` -- the full
  evaluation pipeline (clustering method choice -> capacity-aware repair
  toggle -> NSGA-II -> persistence) used for the Phase 6 evaluation run
  (Fix Pass 4 S7): one `(depot_id, delivery_date, method, capacity_aware,
  seed)` combination per call, one tidy result row out, no pre-aggregation.

Neither layer is the full Phase 5/6 metrics/statistics suite from
BACKEND_REMEDIATION_PROMPT.md -- `statistics.py` (Fix Pass 4 S8) is the
analysis layer on top of this harness's output.
"""
import os

# Set before joblib/numpy/scikit-learn (or any app module importing them).
# Each evaluation run is already parallelized at the process level; allowing
# every worker to create another BLAS thread pool causes oversubscription.
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from joblib import Parallel, delayed, parallel_config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.reproducibility import set_seeds
from app.db.database import Base
from app.db.seed_vehicle_types import VEHICLE_TYPES
from app.evaluation.real_data import real_instance_payloads
from app.evaluation.synthetic_data import generate_synthetic_parcels
from app.evaluation.utilization_ceiling import compute_placement_aware_ceiling, compute_utilization_ceiling
from app.models.load_plan import LoadPlan
from app.optimization.assignment_problem import AssignmentConfig, load_catalog_snapshot, run_nsga2
from app.schemas.parcel import ParcelIn
from app.services import baseline_clustering, clustering_service, vehicle_catalog_service
from app.services.capacity_aware_clustering import RepairConfig, group_by_cluster, repair_clusters
from app.services.clustering_common import ClusteringConfig
from app.services.data_service import upsert_parcel
from app.services.optimization_service import optimize_load
from app.services.vehicle_catalog_service import list_available_types

DEPOT_LAT, DEPOT_LON = 6.9271, 79.8612


def _prepare_warm_clusters(clusters, catalog_rows, capacity_aware: bool, *, seed: int):
    """Apply the ablation switch and always return an explicit audit."""
    if not capacity_aware:
        return clusters, {"enabled": False, "n_split": 0, "n_merged": 0}
    repaired = repair_clusters(
        clusters, catalog_rows, RepairConfig(), DEPOT_LAT, DEPOT_LON, seed=seed,
    )
    return repaired.clusters, {
        "enabled": True,
        "n_split": repaired.n_split,
        "n_merged": repaired.n_merged,
    }


def _parcel_namespace(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(**payload)


def _scratch_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    return engine, session


def _seed_catalog(session) -> None:
    for payload in VEHICLE_TYPES:
        vehicle_catalog_service.upsert_type(session, payload)


def evaluation_catalog_snapshot():
    """Exact seeded catalog used by evaluation runs, for batch manifests."""
    engine, session = _scratch_db()
    try:
        _seed_catalog(session)
        return load_catalog_snapshot(session, depot_id=None)
    finally:
        session.close()
        engine.dispose()


def _build_catalog_and_parcels(
    n_parcels: int, seed: int, n_clusters: int, *, synthetic: bool = False,
    depot_id: str = "D-CMB-001", delivery_date: str = "2026-01-05",
):
    """Real 7-row catalog (loaded via a scratch in-memory DB, same access
    path production uses -- `load_catalog_snapshot`) plus parcels, built as
    plain namespaces so the GA never needs a DB session in its hot path.

    Fix Pass 4 S5: real data (`data/parcels_sample_36000.csv`) by default --
    `n_parcels`/`n_clusters`/`seed` are ignored in that case (an instance is
    exactly 400 real parcels; pass `synthetic=True` for the old
    parameterized synthetic generator instead)."""
    engine, session = _scratch_db()
    try:
        _seed_catalog(session)
        catalog = load_catalog_snapshot(session, depot_id=None)
    finally:
        session.close()
        engine.dispose()

    if synthetic:
        payloads = generate_synthetic_parcels(
            n=n_parcels, seed=seed, n_clusters=n_clusters, with_dimensions=True,
            hazmat_fraction=0.03, refrigeration_fraction=0.04, non_stackable_fraction=0.05,
        )
    else:
        payloads = real_instance_payloads(depot_id, delivery_date)
    parcels = [_parcel_namespace(p) for p in payloads]
    return catalog, parcels


@dataclass
class RunConfig:
    n_parcels: int = 400
    instance_seed: int = 0
    ga_seed: int = 0
    n_clusters: int = 8
    population: int = 100
    generations: int = 200
    synthetic: bool = False
    depot_id: str = "D-CMB-001"
    delivery_date: str = "2026-01-05"
    enforce_weight_order: bool = False
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])


def run_one(cfg: RunConfig) -> dict:
    """Times catalog load + `run_nsga2` for one instance/seed. Returns wall
    time, the slot cache hit rate (B.1), and the placement short-circuit
    rate (B.2)."""
    set_seeds(cfg.instance_seed)
    catalog, parcels = _build_catalog_and_parcels(
        cfg.n_parcels, cfg.instance_seed, cfg.n_clusters,
        synthetic=cfg.synthetic, depot_id=cfg.depot_id, delivery_date=cfg.delivery_date,
    )
    config = AssignmentConfig(
        depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, population=cfg.population,
        generations=cfg.generations, enforce_weight_order=cfg.enforce_weight_order,
    )

    started = time.perf_counter()
    problem, res = run_nsga2(parcels, catalog, config, seed=cfg.ga_seed)
    elapsed = time.perf_counter() - started

    return {
        "run_id": cfg.run_id,
        "n_parcels": len(parcels),
        "instance_seed": cfg.instance_seed,
        "ga_seed": cfg.ga_seed,
        "population": cfg.population,
        "generations": cfg.generations,
        "enforce_weight_order": cfg.enforce_weight_order,
        "elapsed_seconds": elapsed,
        "cache_hit_rate": problem.cache_hit_rate(),
        "short_circuit_rate": problem.short_circuit_rate(),
        "cache_hits": problem._cache_hits,
        "cache_misses": problem._cache_misses,
        "n_pareto_solutions": len(res.F) if res.F is not None else 0,
    }


def run_batch(configs: list[RunConfig], *, n_jobs: int = -1, out_dir: str | Path | None = None) -> list[dict]:
    """B.3: each `(instance, seed)` run is independent -- parallelized at the
    harness level (not inside pymoo, which would add overhead the per-run
    parallelism doesn't). Each worker writes its own result file; nothing
    shares a file handle across workers."""
    out_path = Path(out_dir) if out_dir else None
    if out_path:
        out_path.mkdir(parents=True, exist_ok=True)

    def _run_and_write(cfg: RunConfig) -> dict:
        result = run_one(cfg)
        if out_path:
            (out_path / f"{cfg.run_id}.json").write_text(json.dumps(result, indent=2))
        return result

    with parallel_config(backend="loky", inner_max_num_threads=1):
        return Parallel(n_jobs=n_jobs)(delayed(_run_and_write)(cfg) for cfg in configs)


def merge_results(out_dir: str | Path) -> list[dict]:
    out_path = Path(out_dir)
    return [json.loads(p.read_text()) for p in sorted(out_path.glob("*.json"))]


# --------------------------------------------------------------------------
# Full pipeline (Fix Pass 4 S7): clustering method x capacity-aware toggle
# x seed, over real instances, ending in a persisted LoadPlan.
# --------------------------------------------------------------------------


@dataclass
class PipelineRunConfig:
    depot_id: str
    delivery_date: str  # 'YYYY-MM-DD', matching the CSV
    method: str  # "hdbscan" | "kmeans"
    capacity_aware: bool
    seed: int
    population: int = 100
    generations: int = 200
    enforce_weight_order: bool = False

    @property
    def run_id(self) -> str:
        """Deterministic, not random -- this is what makes `run_pipeline_batch`'s
        resume support work: the same config always maps to the same
        filename, so a completed run is recognized on a re-run without
        tracking state anywhere else."""
        cap = "cap1" if self.capacity_aware else "cap0"
        return f"{self.depot_id}_{self.delivery_date}_{self.method}_{cap}_seed{self.seed}"


def run_pipeline_one(cfg: PipelineRunConfig) -> dict:
    """One full pipeline run: real instance -> clustering (method) ->
    capacity-aware repair (if capacity_aware) -> NSGA-II (warm-started from
    the resulting clusters) -> persisted LoadPlan. Returns one tidy result
    row -- no pre-aggregation, that's `statistics.py`'s job (S8)."""
    set_seeds(cfg.seed)
    engine, session = _scratch_db()
    try:
        _seed_catalog(session)
        catalog_rows = list_available_types(session, depot_id=None)
        catalog = load_catalog_snapshot(session, depot_id=None)

        payloads = real_instance_payloads(cfg.depot_id, cfg.delivery_date)
        parcels = [upsert_parcel(session, ParcelIn(**p)) for p in payloads]
        session.commit()
        delivery_date = date.fromisoformat(cfg.delivery_date)

        mean_capacity_m3 = sum(r.capacity_m3 for r in catalog_rows) / len(catalog_rows)
        clustering_config = ClusteringConfig(
            depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON,
            mean_vehicle_capacity_m3=mean_capacity_m3 if cfg.method == "kmeans" else None,
        )
        cluster_fn = clustering_service.cluster if cfg.method == "hdbscan" else baseline_clustering.cluster

        started = time.perf_counter()
        cluster_fn(parcels, cfg.seed, clustering_config)
        clusters = group_by_cluster(parcels)

        warm_clusters, repair_audit = _prepare_warm_clusters(
            clusters, catalog_rows, cfg.capacity_aware, seed=cfg.seed,
        )

        ga_config = AssignmentConfig(
            depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, population=cfg.population, generations=cfg.generations,
            enforce_weight_order=cfg.enforce_weight_order,
        )
        result, _virtual_vehicles = optimize_load(
            session, parcels,
            depot_id=cfg.depot_id, depot_lat=DEPOT_LAT, depot_lon=DEPOT_LON, delivery_date=delivery_date,
            clustering_method=cfg.method, seed=cfg.seed, config=ga_config, warm_start_clusters=warm_clusters,
        )
        elapsed = time.perf_counter() - started

        plan = session.query(LoadPlan).filter_by(plan_id=result["plan_id"]).first()

        total_weight = sum(p.weight_kg for p in parcels)
        total_volume = sum(p.volume_m3 for p in parcels)
        capacity_ceiling = compute_utilization_ceiling(total_weight, total_volume, catalog)
        placement_ceiling = compute_placement_aware_ceiling(
            parcels, catalog, enforce_weight_order=cfg.enforce_weight_order,
        )
        achieved_vs_placement = (
            plan.mean_utilization / placement_ceiling.utilization if placement_ceiling.utilization else 0.0
        )
        achieved_vs_capacity = (
            plan.mean_utilization / capacity_ceiling.utilization if capacity_ceiling.utilization else 0.0
        )

        return {
            "run_id": cfg.run_id,
            "depot_id": cfg.depot_id,
            "delivery_date": cfg.delivery_date,
            "method": cfg.method,
            "capacity_aware": cfg.capacity_aware,
            "seed": cfg.seed,
            "enforce_weight_order": cfg.enforce_weight_order,
            "n_parcels": len(parcels),
            "mean_utilization": plan.mean_utilization,
            # Legacy alias retained so existing pilot files remain readable.
            "utilization_ceiling": capacity_ceiling.utilization,
            "utilization_ceiling_capacity": capacity_ceiling.utilization,
            "utilization_greedy_reference": placement_ceiling.utilization,
            "achieved_vs_greedy_reference": achieved_vs_placement,
            "achieved_vs_capacity_ceiling": achieved_vs_capacity,
            "total_distance_km": plan.total_distance_km,
            "mean_time_window_compliance": plan.mean_time_window_compliance,
            "total_fleet_cost": plan.total_fleet_cost,
            "n_vehicles": plan.n_vehicles,
            "hypervolume": plan.hypervolume,
            "pareto_front_size": result["pareto_front_size"],
            "feasible_individuals_final": result["feasible_individuals_final"],
            "slot_budget": result["slot_budget"],
            "parcels_per_slot": result["parcels_per_slot"],
            "runtime_seconds": elapsed,
            "repair_audit": repair_audit,
        }
    finally:
        session.close()
        engine.dispose()


def run_pipeline_batch(
    configs: list[PipelineRunConfig], *, n_jobs: int = -1, out_dir: str | Path,
) -> list[dict]:
    """S7: resume-capable -- a config whose result file already exists in
    `out_dir` is skipped, not re-run, so a failure partway through a long
    batch doesn't mean starting over."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    pending = [cfg for cfg in configs if not (out_path / f"{cfg.run_id}.json").exists()]

    def _run_and_write(cfg: PipelineRunConfig) -> dict:
        result = run_pipeline_one(cfg)
        (out_path / f"{cfg.run_id}.json").write_text(json.dumps(result, indent=2))
        return result

    if pending:
        with parallel_config(backend="loky", inner_max_num_threads=1):
            Parallel(n_jobs=n_jobs)(delayed(_run_and_write)(cfg) for cfg in pending)

    return [json.loads((out_path / f"{cfg.run_id}.json").read_text()) for cfg in configs]
