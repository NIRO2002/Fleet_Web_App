"""Fix Pass 4 item S8: statistics.py correctness, on controlled synthetic
result rows (not the real pilot output -- that's exercised end-to-end
separately). Validates the Wilcoxon/effect-size/Holm-correction machinery
against hand-computable cases before trusting it on real results."""
import pytest

from app.evaluation.statistics import (
    ComparisonRow,
    aggregate_median_by_instance,
    holm_bonferroni,
    infeasibility_by_arm,
    run_h1_clustering_comparison,
    run_h2_capacity_aware_ablation,
    to_markdown_table,
)


def _row(depot_id, delivery_date, method, capacity_aware, seed, **metrics):
    base = {
        "mean_utilization": 0.5, "total_distance_km": 100.0, "mean_time_window_compliance": 0.9,
        "total_fleet_cost": 1000.0, "n_vehicles": 5, "hypervolume": 0.1, "runtime_seconds": 60.0,
        "utilization_ceiling_capacity": 0.95, "utilization_greedy_reference": 0.6,
        "achieved_vs_greedy_reference": 0.5 / 0.6, "feasible": True,
    }
    base.update(metrics)
    return {
        "depot_id": depot_id, "delivery_date": delivery_date, "method": method,
        "capacity_aware": capacity_aware, "seed": seed, **base,
    }


def test_aggregate_median_by_instance_uses_median_not_mean():
    """A single outlier seed must not move the aggregate as much as a mean would."""
    rows = [
        _row("D1", "2026-01-01", "hdbscan", True, seed=0, mean_utilization=0.50),
        _row("D1", "2026-01-01", "hdbscan", True, seed=1, mean_utilization=0.52),
        _row("D1", "2026-01-01", "hdbscan", True, seed=2, mean_utilization=0.99),  # outlier
    ]
    agg = aggregate_median_by_instance(rows, method="hdbscan", capacity_aware=True)
    assert agg[("D1", "2026-01-01")]["mean_utilization"] == 0.52, "median of [0.50, 0.52, 0.99] is 0.52"


def test_holm_bonferroni_matches_hand_computed_example():
    """Classic textbook example: p = [0.01, 0.04, 0.03, 0.005], m=4.
    Sorted: 0.005, 0.01, 0.03, 0.04 -> multipliers 4,3,2,1 ->
    raw adjusted: 0.02, 0.03, 0.06, 0.04 -> step-down monotonic max:
    0.02, 0.03, 0.06, 0.06."""
    p_values = [0.01, 0.04, 0.03, 0.005]
    adjusted = holm_bonferroni(p_values)
    # re-associate with original order: index 3 (0.005) -> 0.02, index 0 (0.01) -> 0.03,
    # index 2 (0.03) -> 0.06, index 1 (0.04) -> 0.06
    assert adjusted[3] == pytest.approx(0.02)
    assert adjusted[0] == pytest.approx(0.03)
    assert adjusted[2] == pytest.approx(0.06)
    assert adjusted[1] == pytest.approx(0.06)


def test_holm_bonferroni_caps_at_one():
    adjusted = holm_bonferroni([0.9, 0.8, 0.99])
    assert all(a <= 1.0 for a in adjusted)


def test_h1_clustering_comparison_detects_a_consistent_hdbscan_advantage():
    """Constructed so HDBSCAN's utilization is consistently higher than
    K-Means across every instance -- Wilcoxon must detect this as
    significant with a positive effect size (HDBSCAN > K-Means)."""
    rows = []
    for i in range(8):
        depot, date = f"D{i}", "2026-01-01"
        for seed in range(3):
            rows.append(_row(depot, date, "hdbscan", True, seed, mean_utilization=0.70 + 0.01 * seed))
            rows.append(_row(depot, date, "kmeans", True, seed, mean_utilization=0.50 + 0.01 * seed))

    results = run_h1_clustering_comparison(rows, capacity_aware=True)
    util_row = next(r for r in results if r.metric_key == "mean_utilization")
    assert util_row.n == 8
    assert util_row.median_a > util_row.median_b  # HDBSCAN (a) > K-Means (b)
    assert util_row.effect_size > 0.9, "an almost-perfectly-consistent advantage should show a strong effect size"
    assert util_row.p_value < 0.05
    assert util_row.direction == "HDBSCAN > K-Means"
    assert util_row.n_zero_diffs == 0


def test_h2_capacity_aware_ablation_reports_no_difference_honestly():
    """When the two arms are identical, the comparison must report 'no
    difference' with a near-zero effect size, not manufacture a spurious
    result -- this is the "report what you get" integrity requirement."""
    rows = []
    for i in range(6):
        depot, date = f"D{i}", "2026-01-01"
        for seed in range(3):
            rows.append(_row(depot, date, "hdbscan", True, seed, total_distance_km=100.0 + i))
            rows.append(_row(depot, date, "hdbscan", False, seed, total_distance_km=100.0 + i))

    results = run_h2_capacity_aware_ablation(rows, method="hdbscan")
    distance_row = next(r for r in results if r.metric_key == "total_distance_km")
    assert distance_row.effect_size == pytest.approx(0.0)
    assert distance_row.direction == "no difference"
    assert distance_row.n_zero_diffs == distance_row.n, "every pair is an exact tie"


def test_markdown_table_renders_every_metric():
    rows = [
        ComparisonRow(
            metric_key="mean_utilization", metric_label="Utilization", n=5,
            median_a=0.7, iqr_a=0.1, median_b=0.5, iqr_b=0.1,
            statistic=3.0, p_value=0.02, p_value_adjusted=0.04, effect_size=0.6,
            n_zero_diffs=0, direction="HDBSCAN > K-Means",
        )
    ]
    table = to_markdown_table(rows, label_a="HDBSCAN", label_b="K-Means", title="H1: Clustering")
    assert "Utilization" in table
    assert "HDBSCAN > K-Means" in table
    assert "0.6" in table


def test_run_h1_raises_on_no_shared_instances():
    rows = [_row("D1", "2026-01-01", "hdbscan", True, seed=0)]  # no K-Means rows at all
    with pytest.raises(ValueError):
        run_h1_clustering_comparison(rows, capacity_aware=True)


def test_infeasible_rows_are_flagged_counted_and_excluded():
    rows = [
        _row("D1", "2026-01-01", "hdbscan", True, 0, mean_utilization=0.5),
        _row("D1", "2026-01-01", "hdbscan", True, 1, mean_utilization=0.99, feasible=False),
        _row("D1", "2026-01-01", "hdbscan", True, 2, mean_utilization=0.6),
    ]
    aggregate = aggregate_median_by_instance(rows, method="hdbscan", capacity_aware=True)
    assert aggregate[("D1", "2026-01-01")]["mean_utilization"] == pytest.approx(0.55)
    summary = infeasibility_by_arm(rows)
    assert summary[("hdbscan", True)] == {"total": 3, "infeasible": 1, "rate": pytest.approx(1 / 3)}
