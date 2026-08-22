"""Paired statistical analysis for evaluation result rows.

The reported family is the ten metrics in :data:`METRICS`; Holm correction
is applied once across that complete family for each stated hypothesis.
Infeasible observations are excluded before seed aggregation. Comparisons
use only instance keys present in both arms, so an incomplete pair is
dropped as a whole and is never imputed.
"""
import statistics as pystats
from dataclasses import dataclass

from scipy.stats import wilcoxon

METRICS = {
    "mean_utilization": "Utilization",
    "achieved_vs_greedy_reference": "Achieved / greedy reference",
    "utilization_greedy_reference": "Greedy attainable reference",
    "utilization_ceiling_capacity": "Capacity-only theoretical maximum",
    "total_distance_km": "Distance (km)",
    "mean_time_window_compliance": "Compliance",
    "total_fleet_cost": "Fleet cost",
    "n_vehicles": "Vehicle count",
    "hypervolume": "Hypervolume",
    "runtime_seconds": "Runtime (s)",
}
HOLM_FAMILY = tuple(METRICS)


def _instance_key(row):
    return row["depot_id"], row["delivery_date"]


def aggregate_median_by_instance(rows, *, method, capacity_aware, full_seed_count=None):
    arm_rows = [row for row in rows if row["method"] == method and row["capacity_aware"] == capacity_aware]
    if full_seed_count is None:
        full_seed_count = len({row["seed"] for row in arm_rows})
    grouped = {}
    for row in arm_rows:
        if not row.get("feasible", True):
            continue
        bucket = grouped.setdefault(_instance_key(row), {metric: [] for metric in METRICS})
        for metric in METRICS:
            bucket[metric].append(row[metric])
    aggregates = {}
    for key, values in grouped.items():
        n_seeds = len(values[next(iter(METRICS))])
        aggregates[key] = {m: pystats.median(v) for m, v in values.items()}
        aggregates[key]["n_seeds"] = n_seeds
        aggregates[key]["full_seed_count"] = full_seed_count
        aggregates[key]["seed_count_below_half"] = bool(full_seed_count and n_seeds < full_seed_count / 2)
    return aggregates


def seed_count_distribution(rows, *, full_seed_count=None):
    """Summarise feasible seed contributions across every instance/arm cell."""
    counts = []
    below_full = []
    below_half = []
    arms = sorted({(row["method"], row["capacity_aware"]) for row in rows})
    inferred_full = full_seed_count or len({row["seed"] for row in rows})
    for method, capacity_aware in arms:
        aggregated = aggregate_median_by_instance(
            rows, method=method, capacity_aware=capacity_aware,
            full_seed_count=inferred_full,
        )
        for instance, cell in aggregated.items():
            count = cell["n_seeds"]
            counts.append(count)
            identity = {"instance": instance, "method": method, "capacity_aware": capacity_aware, "n_seeds": count}
            if count < inferred_full:
                below_full.append(identity)
            if cell["seed_count_below_half"]:
                below_half.append(identity)
    return {
        "full_seed_count": inferred_full,
        "minimum": min(counts) if counts else 0,
        "median": pystats.median(counts) if counts else 0,
        "cells_below_full_count": len(below_full),
        "below_full_cells": below_full,
        "below_half_cells": below_half,
    }


def paired_instance_audit(a, b):
    """Return the exact complete-pair set and arm-specific dropped keys."""
    a_keys, b_keys = set(a), set(b)
    return {
        "paired_instances": sorted(a_keys & b_keys),
        "dropped_missing_from_a": sorted(b_keys - a_keys),
        "dropped_missing_from_b": sorted(a_keys - b_keys),
        "n_dropped_pairs": len(a_keys ^ b_keys),
    }


def infeasibility_by_arm(rows):
    arms = {}
    for row in rows:
        bucket = arms.setdefault((row["method"], row["capacity_aware"]), {"total": 0, "infeasible": 0, "rate": 0.0})
        bucket["total"] += 1
        bucket["infeasible"] += row.get("feasible", True) is not True
    for bucket in arms.values():
        bucket["rate"] = bucket["infeasible"] / bucket["total"] if bucket["total"] else 0.0
    return arms


def holm_bonferroni(p_values):
    order = sorted(range(len(p_values)), key=p_values.__getitem__)
    adjusted, running = [0.0] * len(p_values), 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p_values) - rank) * p_values[index])
        adjusted[index] = min(1.0, running)
    return adjusted


def _rank_biserial(a, b):
    diffs = [x - y for x, y in zip(a, b)]
    nonzero = [d for d in diffs if d]
    if not nonzero:
        return 0.0, len(diffs)
    order = sorted(range(len(nonzero)), key=lambda i: abs(nonzero[i]))
    ranks = [0.0] * len(nonzero)
    i = 0
    while i < len(order):
        j = i
        while j < len(order) and abs(nonzero[order[j]]) == abs(nonzero[order[i]]):
            j += 1
        for k in range(i, j):
            ranks[order[k]] = (i + 1 + j) / 2
        i = j
    positive = sum(r for r, d in zip(ranks, nonzero) if d > 0)
    negative = sum(r for r, d in zip(ranks, nonzero) if d < 0)
    return (positive - negative) / (positive + negative), len(diffs) - len(nonzero)


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
    direction: str
    seed_counts_a: tuple[int, ...] = ()
    seed_counts_b: tuple[int, ...] = ()


def _iqr(values):
    if len(values) < 2:
        return 0.0
    q = pystats.quantiles(values, n=4, method="inclusive")
    return q[2] - q[0]


def compare(a, b, *, label_a, label_b):
    audit = paired_instance_audit(a, b)
    shared = audit["paired_instances"]
    if not shared:
        raise ValueError("No instances present in both arms of the comparison.")
    rows = []
    for key, label in METRICS.items():
        va, vb = [a[i][key] for i in shared], [b[i][key] for i in shared]
        effect, zeros = _rank_biserial(va, vb)
        if zeros == len(shared):
            statistic, p_value = 0.0, 1.0
        else:
            result = wilcoxon(va, vb, zero_method="wilcox")
            statistic, p_value = float(result.statistic), float(result.pvalue)
        direction = f"{label_a} > {label_b}" if effect > 1e-9 else f"{label_b} > {label_a}" if effect < -1e-9 else "no difference"
        rows.append(ComparisonRow(
            key, label, len(shared), pystats.median(va), _iqr(va),
            pystats.median(vb), _iqr(vb), statistic, p_value, p_value,
            effect, zeros, direction,
            tuple(a[i]["n_seeds"] for i in shared),
            tuple(b[i]["n_seeds"] for i in shared),
        ))
    for row, adjusted in zip(rows, holm_bonferroni([r.p_value for r in rows])):
        row.p_value_adjusted = adjusted
    return rows


def run_h1_clustering_comparison(rows, *, capacity_aware=True):
    a = aggregate_median_by_instance(rows, method="hdbscan", capacity_aware=capacity_aware)
    b = aggregate_median_by_instance(rows, method="kmeans", capacity_aware=capacity_aware)
    return compare(a, b, label_a="HDBSCAN", label_b="K-Means")


def run_h2_capacity_aware_ablation(rows, *, method="hdbscan"):
    a = aggregate_median_by_instance(rows, method=method, capacity_aware=True)
    b = aggregate_median_by_instance(rows, method=method, capacity_aware=False)
    return compare(a, b, label_a="capacity-aware on", label_b="capacity-aware off")


def to_markdown_table(rows, *, label_a, label_b, title):
    def seed_summary(values):
        return f"{min(values)}/{pystats.median(values):g}/{max(values)}" if values else "n/a"
    lines = [f"### {title}", "", f"Holm family: {', '.join(HOLM_FAMILY)}.", "", "Seed columns show minimum/median/maximum feasible seeds contributing per paired instance; cells below half the configured seed count must be flagged in the accompanying seed audit.", "", f"| Metric | n | seeds ({label_a}) | seeds ({label_b}) | median ({label_a}) | IQR ({label_a}) | median ({label_b}) | IQR ({label_b}) | W | p (raw) | p (Holm) | effect size (r) | direction | zero diffs |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|"]
    for r in rows:
        lines.append(f"| {r.metric_label} | {r.n} | {seed_summary(r.seed_counts_a)} | {seed_summary(r.seed_counts_b)} | {r.median_a:.4g} | {r.iqr_a:.4g} | {r.median_b:.4g} | {r.iqr_b:.4g} | {r.statistic:.4g} | {r.p_value:.4g} | {r.p_value_adjusted:.4g} | {r.effect_size:.3f} | {r.direction} | {r.n_zero_diffs} |")
    return "\n".join(lines)
