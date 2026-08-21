import os
from types import SimpleNamespace

from app.evaluation import harness


def test_evaluation_workers_limit_numerical_thread_pools():
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        assert os.environ[name] == "1"


def test_capacity_aware_audit_carries_current_cluster_status(monkeypatch):
    repaired = SimpleNamespace(clusters={1: [object()]}, n_split=1, n_merged=2,
        clusters_before=1, clusters_after=1, cluster_status={1: {"feasible": True, "reason": None}},
        excluded_infeasible_count=0)
    monkeypatch.setattr(harness, "repair_clusters", lambda *args, **kwargs: repaired)
    clusters, audit = harness._prepare_warm_clusters({0: [object()]}, [], True,
        depot_lat=1., depot_lon=2., seed=7)
    assert clusters == repaired.clusters
    assert audit["n_split"] == 1 and audit["n_merged"] == 2
    assert audit["cluster_status"] == repaired.cluster_status


def test_parallelism_is_gated_until_stage_four():
    try:
        harness.run_pipeline_batch([], n_jobs=2, out_dir="unused")
    except ValueError as error:
        assert "Stage 4" in str(error)
    else:
        raise AssertionError("parallel execution must remain gated")
