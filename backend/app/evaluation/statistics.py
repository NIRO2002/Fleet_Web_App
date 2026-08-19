"""Statistical analysis of evaluation harness results (Fix Pass 4 item S8 --
Specific Objective 5). Reads `harness.run_pipeline_batch`'s per-run result
rows, aggregates to one value per `(instance, method, capacity_aware)` via
the median across seeds, and runs two paired Wilcoxon signed-rank
comparisons across instances:

- H1 (clustering): HDBSCAN vs K-Means, capacity-aware held constant.
- H2 (ablation): capacity-aware on vs off, HDBSCAN held constant.

Every p-value is reported alongside its matched-pairs rank-biserial
correlation (effect size) and its Holm-Bonferroni-adjusted value across the
metric family within that hypothesis -- a p-value alone is not a result.

Report whatever the data actually shows. Do not add metrics after seeing
results, drop instances, or select seeds.
"""
import statistics as pystats
from dataclasses import dataclass

from scipy.stats import wilcoxon

#: One row per (instance, method, capacity_aware, seed) result is expected
#: to carry these keys (matches harness.run_pipeline_one's output).
METRICS = {
    "mean_utilization": "Utilization",
    "achieved_vs_placement_ceiling": "Achieved / placement-aware reference",
    "utilization_ceiling_placement": "Placement-aware attainable reference",
    "utilization_ceiling_capacity": "Capacity-only theoretical maximum",
    "total_distance_km": "Distance (km)",
    "mean_time_window_compliance": "Compliance",
    "total_fleet_cost": "Fleet cost",
    "n_vehicles": "Vehicle count",
    "hypervolume": "Hypervolume",
    "runtime_seconds": "Runtime (s)",
}


def _instance_key(row: dict) -> tuple[str, str]:
    return row["depot_id"], row["delivery_date"]


def aggregate_median_by_instance(
    rows: list[dict], *, method: str, capacity_aware: bool
) -> dict[tuple[str, str], dict[str, float]]:
    """One row per instance: the median across every seed's result for this
    `(method, capacity_aware)` combination. Median, not mean -- GA outcomes
    are not normally distributed and a single bad seed shouldn't move the
    estimate."""
    by_instance: dict[tuple[str, str], dict[str, list[float]]] = {}
    for row in rows:
        if row["method"] != method or row["capacity_aware"] != capacity_aware:
            continue
        key = _instance_key(row)
        bucket = by_instance.setdefault(key, {m: [] for m in METRICS})
        for metric in METRICS:
            bucket[metric].append(row[metric])

    return {
        key: {metric: pystats.median(values) for metric, values in metrics.items()}
        for key, metrics in by_instance.items()
    }


def _rank_biserial_effect_size(a: list[float], b: list[float]) -> tuple[float, int]:
    """Matched-pairs rank-biserial correlation r = (W+ - W-) / (W+ + W-),
    computed directly from signed-rank sums (not derived from scipy's own
    W statistic, which reports only min(W+, W-) and drops the sign).
    Returns (r, n_zero_diffs) -- `wilcoxon` itself silently drops
    zero-difference pairs, so the count is reported separately."""
    diffs = [x - y for x, y in zip(a, b)]
    nonzero = [d for d in diffs if d != 0]
    n_zero = len(diffs) - len(nonzero)
    if not nonzero:
        return 0.0, n_zero

    ranked = sorted(range(len(nonzero)), key=lambda i: abs(nonzero[i]))
    ranks = [0.0] * len(nonzero)
    i = 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and abs(nonzero[ranked[j]]) == abs(nonzero[ranked[i]]):
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[ranked[k]] = avg_rank
        i = j

    w_pos = sum(r for r, d in zip(ranks, nonzero) if d > 0)
    w_neg = sum(r for r, d in zip(ranks, nonzero) if d < 0)
    total = w_pos + w_neg
    r = (w_pos - w_neg) / total if total else 0.0
    return r, n_zero


def holm_bonferroni(p_values: list[float]) -> list[float]:
    """Step-down Holm-Bonferroni correction. Returns adjusted p-values in
    the SAME order as the input (not sorted), each capped at 1.0 and
    enforced monotonic non-decreasing in rank order, per the standard
    procedure."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running_max = 0.0
    for rank, idx in enumerate(order):
        candidate = (m - rank) * p_values[idx]
        running_max = max(running_max, candidate)
        adjusted[idx] = min(1.0, running_max)
    return adjusted


@dataclass
class ComparisonRow:
    metric_key: str
    metric_label: str
    n: int
    median_a: float
    iqr_a: float
    median_b: float
    iqr_b: float
    statistic: float
    p_value: float
    p_value_adjusted: float
    effect_size: float
    n_zero_diffs: int
    direction: str  # "a > b", "b > a", or "no difference"


def _iqr(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    quantiles = pystats.quantiles(values, n=4, method="inclusive")
    return quantiles[2] - quantiles[0]


def compare(
    aggregated_a: dict[tuple[str, str], dict[str, float]],
    aggregated_b: dict[tuple[str, str], dict[str, float]],
    *, label_a: str, label_b: str,
) -> list[ComparisonRow]:
    """Paired Wilcoxon signed-rank test per metric, across every instance
    present in both `aggregated_a` and `aggregated_b`. Holm-Bonferroni
    correction is applied across the full metric family in one pass, after
    every metric's raw p-value has been computed."""
    shared_instances = sorted(set(aggregated_a) & set(aggregated_b))
    if len(shared_instances) < 1:
        raise ValueError("No instances present in both arms of the comparison.")

    raw_rows = []
    for metric_key, metric_label in METRICS.items():
        values_a = [aggregated_a[inst][metric_key] for inst in shared_instances]
        values_b = [aggregated_b[inst][metric_key] for inst in shared_instances]

        effect_size, n_zero = _rank_biserial_effect_size(values_a, values_b)
        n_nonzero_diffs = len(shared_instances) - n_zero
        if n_nonzero_diffs == 0:
            # Every pair identical -- scipy's wilcoxon divides by a
            # zero standard error here (a RuntimeWarning, not a raised
            # exception, so it must be checked for explicitly rather than
            # caught) rather than returning a meaningful result.
            statistic, p_value = 0.0, 1.0
        else:
            result = wilcoxon(values_a, values_b, zero_method="wilcox")
            statistic, p_value = float(result.statistic), float(result.pvalue)

        if effect_size > 1e-9:
            direction = f"{label_a} > {label_b}"
        elif effect_size < -1e-9:
            direction = f"{label_b} > {label_a}"
        else:
            direction = "no difference"

        raw_rows.append(
            ComparisonRow(
                metric_key=metric_key, metric_label=metric_label, n=len(shared_instances),
                median_a=pystats.median(values_a), iqr_a=_iqr(values_a),
                median_b=pystats.median(values_b), iqr_b=_iqr(values_b),
                statistic=statistic, p_value=p_value, p_value_adjusted=p_value,
                effect_size=effect_size, n_zero_diffs=n_zero, direction=direction,
            )
        )

    adjusted = holm_bonferroni([row.p_value for row in raw_rows])
    for row, adj in zip(raw_rows, adjusted):
        row.p_value_adjusted = adj
    return raw_rows


def to_markdown_table(rows: list[ComparisonRow], *, label_a: str, label_b: str, title: str) -> str:
    lines = [
        f"### {title}",
        "",
        f"| Metric | n | median ({label_a}) | IQR ({label_a}) | median ({label_b}) | IQR ({label_b}) "
        "| W | p (raw) | p (Holm) | effect size (r) | direction | zero diffs |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.metric_label} | {row.n} | {row.median_a:.4g} | {row.iqr_a:.4g} | "
            f"{row.median_b:.4g} | {row.iqr_b:.4g} | {row.statistic:.4g} | {row.p_value:.4g} | "
            f"{row.p_value_adjusted:.4g} | {row.effect_size:.3f} | {row.direction} | {row.n_zero_diffs} |"
        )
    return "\n".join(lines)


def run_h1_clustering_comparison(rows: list[dict], *, capacity_aware: bool = True) -> list[ComparisonRow]:
    """H1: HDBSCAN vs K-Means, capacity-aware held constant."""
    hdbscan = aggregate_median_by_instance(rows, method="hdbscan", capacity_aware=capacity_aware)
    kmeans = aggregate_median_by_instance(rows, method="kmeans", capacity_aware=capacity_aware)
    return compare(hdbscan, kmeans, label_a="HDBSCAN", label_b="K-Means")


def run_h2_capacity_aware_ablation(rows: list[dict], *, method: str = "hdbscan") -> list[ComparisonRow]:
    """H2: capacity-aware split/merge on vs off, clustering method held
    constant -- the ablation that evidences the split-and-merge
    contribution."""
    on = aggregate_median_by_instance(rows, method=method, capacity_aware=True)
    off = aggregate_median_by_instance(rows, method=method, capacity_aware=False)
    return compare(on, off, label_a="capacity-aware on", label_b="capacity-aware off")
