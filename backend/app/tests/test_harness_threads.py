import os
from types import SimpleNamespace

from app.evaluation import harness


def test_evaluation_workers_limit_numerical_thread_pools():
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        assert os.environ[name] == "1"


def test_capacity_aware_audit_differs_when_repair_fires(monkeypatch):
    clusters = {0: [object()]}
    repaired = SimpleNamespace(clusters={1: [object()]}, n_split=1, n_merged=2)
    monkeypatch.setattr(harness, "repair_clusters", lambda *args, **kwargs: repaired)

    off_clusters, off_audit = harness._prepare_warm_clusters(clusters, [], False)
    on_clusters, on_audit = harness._prepare_warm_clusters(clusters, [], True)

    assert off_clusters is clusters
    assert on_clusters is repaired.clusters
    assert off_audit == {"enabled": False, "n_split": 0, "n_merged": 0}
    assert on_audit == {"enabled": True, "n_split": 1, "n_merged": 2}
    assert on_audit != off_audit
