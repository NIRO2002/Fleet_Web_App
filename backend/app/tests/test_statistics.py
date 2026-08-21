import pytest

from app.evaluation.statistics import (
    HOLM_FAMILY, aggregate_median_by_instance, holm_bonferroni,
    infeasibility_by_arm, paired_instance_audit, run_h1_clustering_comparison,
)


def _row(depot, method, seed, *, feasible=True, capacity=True, value=.5):
    return {"depot_id": depot, "delivery_date": "2026-01-01", "method": method,
            "capacity_aware": capacity, "seed": seed, "feasible": feasible,
            "mean_utilization": value, "achieved_vs_greedy_reference": value,
            "utilization_greedy_reference": .6, "utilization_ceiling_capacity": .95,
            "total_distance_km": 100., "mean_time_window_compliance": .9,
            "total_fleet_cost": 1000., "n_vehicles": 5, "hypervolume": .1,
            "runtime_seconds": 60.}


def test_aggregate_uses_median_and_excludes_infeasible():
    rows = [_row("D1", "hdbscan", 0, value=.5), _row("D1", "hdbscan", 1, value=.6),
            _row("D1", "hdbscan", 2, feasible=False, value=.99)]
    result = aggregate_median_by_instance(rows, method="hdbscan", capacity_aware=True)
    assert result[("D1", "2026-01-01")]["mean_utilization"] == pytest.approx(.55)
    assert infeasibility_by_arm(rows)[("hdbscan", True)]["infeasible"] == 1


def test_incomplete_instance_is_dropped_as_an_entire_pair():
    rows = []
    for depot in ("D1", "D2"):
        rows += [_row(depot, "hdbscan", seed) for seed in range(3)]
    rows += [_row("D1", "kmeans", seed) for seed in range(3)]
    h = aggregate_median_by_instance(rows, method="hdbscan", capacity_aware=True)
    k = aggregate_median_by_instance(rows, method="kmeans", capacity_aware=True)
    audit = paired_instance_audit(h, k)
    assert audit["paired_instances"] == [("D1", "2026-01-01")]
    assert audit["dropped_missing_from_b"] == [("D2", "2026-01-01")]
    assert audit["n_dropped_pairs"] == 1
    assert all(row.n == 1 for row in run_h1_clustering_comparison(rows))


def test_holm_is_full_stated_metric_family():
    assert len(HOLM_FAMILY) == 10
    adjusted = holm_bonferroni([.01, .04, .03, .005])
    assert adjusted == pytest.approx([.03, .06, .06, .02])
