import os
from types import SimpleNamespace

from app.evaluation import harness
from app.evaluation.feature_set_downstream_study import study_configs


def test_evaluation_workers_limit_numerical_thread_pools():
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        assert os.environ[name] == "1"


def test_capacity_aware_audit_carries_current_cluster_status(monkeypatch):
    repaired = SimpleNamespace(clusters={1: [object()]}, n_split=1, n_merged=2,
        clusters_before=1, clusters_after=1, cluster_status={1: {"feasible": True, "reason": None}},
        excluded_infeasible_count=0, audit=[{"temporal_split_predicate_fired": True}])
    monkeypatch.setattr(harness, "repair_clusters", lambda *args, **kwargs: repaired)
    clusters, audit = harness._prepare_warm_clusters({0: [object()]}, [], True,
        depot_lat=1., depot_lon=2., seed=7)
    assert clusters == repaired.clusters
    assert audit["n_split"] == 1 and audit["n_merged"] == 2
    assert audit["cluster_status"] == repaired.cluster_status
    assert audit["audit"] == repaired.audit


def test_parallelism_is_gated_until_stage_four():
    try:
        harness.run_pipeline_batch([], n_jobs=2, out_dir="unused")
    except ValueError as error:
        assert "Stage 4" in str(error)
    else:
        raise AssertionError("parallel execution must remain gated")


def test_feature_set_is_part_of_pipeline_run_identity():
    common = dict(
        depot_id="D-CMB-001", delivery_date="2026-01-05",
        method="hdbscan", capacity_aware=True, seed=7,
    )
    location = harness.PipelineRunConfig(**common, feature_set="location")
    location_time = harness.PipelineRunConfig(**common, feature_set="location_time")

    assert location.run_id != location_time.run_id
    assert "features-location_" in location.run_id
    assert "features-location_time_" in location_time.run_id
    assert harness.PipelineRunConfig(**common).feature_set == "location"


def test_downstream_feature_study_has_fixed_108_run_design():
    configs = study_configs()
    assert len(configs) == 108
    assert len({config.run_id for config in configs}) == 108
    assert all(config.method == "hdbscan" and config.capacity_aware for config in configs)
    assert all(config.include_window_width is False for config in configs)
    assert {(config.feature_set, config.time_weight) for config in configs} == {
        ("location", 5.0), ("location_time", 1.0),
        ("location_time", 5.0), ("location_time", 20.0),
    }


def test_clustering_context_flags_stage_4c_degeneracy():
    clustered = SimpleNamespace(labels=[0] * 7 + [1] * 2 + [-1])
    context = harness._clustering_context([object()] * 10, clustered)
    assert context["max_cluster_share"] == 0.7
    assert context["degenerate"] is True
    assert 0.0 < context["normalized_cluster_size_entropy"] < 1.0
