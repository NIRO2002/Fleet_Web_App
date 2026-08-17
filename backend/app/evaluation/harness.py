"""Fix Pass 2 item B: a minimal harness that makes the GA's runtime,
cache-hit-rate and short-circuit-rate measurable and gives B.3's
`joblib.Parallel` something real to parallelize.

This is deliberately not the full Phase 5/6 evaluation suite (metrics.py /
experiment.py / statistics.py from BACKEND_REMEDIATION_PROMPT.md) -- that
stays out of scope for this pass. `run_one` measures exactly what the Fix
Pass 2 document's runtime numbers describe: catalog load + `run_nsga2`, not
full persistence (`optimize_load` also writes DB rows, which is a separate,
much lower-frequency cost).
"""
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import SimpleNamespace

from joblib import Parallel, delayed
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.reproducibility import set_seeds
from app.db.database import Base
from app.db.seed_vehicle_types import VEHICLE_TYPES
from app.evaluation.synthetic_data import generate_synthetic_parcels
from app.optimization.assignment_problem import AssignmentConfig, load_catalog_snapshot, run_nsga2
from app.services import vehicle_catalog_service


def _parcel_namespace(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(**payload)


def _build_catalog_and_parcels(n_parcels: int, seed: int, n_clusters: int):
    """Real 10-row catalog (loaded via a scratch in-memory DB, same access
    path production uses -- `load_catalog_snapshot`) plus `n_parcels`
    synthetic parcels, built as plain namespaces so the GA never needs a DB
    session in its hot path."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        for payload in VEHICLE_TYPES:
            vehicle_catalog_service.upsert_type(session, payload)
        catalog = load_catalog_snapshot(session, depot_id=None)
    finally:
        session.close()
        engine.dispose()

    payloads = generate_synthetic_parcels(
        n=n_parcels, seed=seed, n_clusters=n_clusters, with_dimensions=True,
        hazmat_fraction=0.03, refrigeration_fraction=0.04, non_stackable_fraction=0.05,
    )
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
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])


def run_one(cfg: RunConfig) -> dict:
    """Times catalog load + `run_nsga2` for one instance/seed. Returns wall
    time, the slot cache hit rate (B.1), and the placement short-circuit
    rate (B.2)."""
    set_seeds(cfg.instance_seed)
    catalog, parcels = _build_catalog_and_parcels(cfg.n_parcels, cfg.instance_seed, cfg.n_clusters)
    config = AssignmentConfig(population=cfg.population, generations=cfg.generations)

    started = time.perf_counter()
    problem, res = run_nsga2(parcels, catalog, config, seed=cfg.ga_seed)
    elapsed = time.perf_counter() - started

    return {
        "run_id": cfg.run_id,
        "n_parcels": cfg.n_parcels,
        "instance_seed": cfg.instance_seed,
        "ga_seed": cfg.ga_seed,
        "population": cfg.population,
        "generations": cfg.generations,
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

    return Parallel(n_jobs=n_jobs)(delayed(_run_and_write)(cfg) for cfg in configs)


def merge_results(out_dir: str | Path) -> list[dict]:
    out_path = Path(out_dir)
    return [json.loads(p.read_text()) for p in sorted(out_path.glob("*.json"))]
