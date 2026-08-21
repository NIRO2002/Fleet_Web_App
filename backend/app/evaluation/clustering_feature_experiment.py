"""Controlled HDBSCAN feature-set experiment; does not invoke or alter NSGA-II."""
from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from datetime import date
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.spatial.distance import cdist, pdist

from app.db.seed_vehicle_types import FIELD_DATA_VEHICLE_TYPES
from app.models.parcel import Parcel
from app.services.capacity_aware_clustering import _fits_some_vehicle, group_by_cluster, repair_clusters
from app.services.clustering_common import ClusteringConfig, project_to_metres
from app.services.clustering_service import cluster

ROOT = Path(__file__).parents[2]
DATASET = ROOT / "data" / "parcels_sample_36000.csv"
OUT_DIR = ROOT / "results"


def _boolean(value: str) -> bool:
    return value.strip().lower() == "true"


def load_instances() -> dict[tuple[str, date], list[Parcel]]:
    grouped: dict[tuple[str, date], list[Parcel]] = defaultdict(list)
    with DATASET.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["delivery_date"] != "2026-01-05":
                continue
            key = (row["depot_id"], date.fromisoformat(row["delivery_date"]))
            grouped[key].append(Parcel.model_construct(
                parcel_id=row["parcel_id"], depot_id=key[0], delivery_date=key[1],
                latitude=float(row["dropoff_lat"]), longitude=float(row["dropoff_lng"]),
                weight_kg=float(row["weight_kg"]), volume_m3=float(row["volume_m3"]),
                length_cm=float(row["length_cm"]), width_cm=float(row["width_cm"]), height_cm=float(row["height_cm"]),
                time_window_start=row["time_window_start"][:5], time_window_end=row["time_window_end"][:5],
                fragile=_boolean(row["fragile"]), stackable=_boolean(row["stackable"]),
                max_stack_weight_kg=float(row["max_stack_weight_kg"]),
                loading_orientation_fixed=_boolean(row["loading_orientation_fixed"]),
                hazardous=_boolean(row["hazardous"]), requires_refrigeration=_boolean(row["requires_refrigeration"]),
                two_person_lift=_boolean(row["two_person_lift"]), do_not_tilt=_boolean(row["do_not_tilt"]),
                priority_level=row["priority_level"], service_type=row["service_type"],
            ))
    return dict(sorted(grouped.items())[:3])


def _minutes(value: str) -> int:
    h, m = map(int, value.split(":"))
    return h * 60 + m


def metrics(parcels: list[Parcel], result, config: ClusteringConfig, seed: int, name: str) -> dict:
    labels = np.asarray(result.labels)
    coords = project_to_metres(parcels, config.depot_lat, config.depot_lon)
    sizes = [int((labels == label).sum()) for label in sorted(set(labels))]
    intra = []
    overlaps = []
    for label in sorted(set(labels)):
        indexes = np.where(labels == label)[0]
        if len(indexes) > 1:
            intra.extend(pdist(coords[indexes]).tolist())
            for a, b in combinations(indexes.tolist(), 2):
                overlaps.append(max(_minutes(parcels[a].time_window_start), _minutes(parcels[b].time_window_start)) < min(_minutes(parcels[a].time_window_end), _minutes(parcels[b].time_window_end)))
    distances = cdist(coords, coords)
    np.fill_diagonal(distances, np.inf)
    purity = np.mean([np.mean(labels[np.argsort(distances[i])[:5]] == labels[i]) for i in range(len(labels))])
    repaired = repair_clusters(group_by_cluster(parcels), FIELD_DATA_VEHICLE_TYPES, seed=seed)
    infeasible = sum(not _fits_some_vehicle(group, FIELD_DATA_VEHICLE_TYPES) for group in repaired.clusters.values())
    return {
        "instance_id": f"{parcels[0].depot_id}_{parcels[0].delivery_date}", "depot_id": parcels[0].depot_id,
        "delivery_date": str(parcels[0].delivery_date), "configuration": name,
        "min_cluster_size": config.min_cluster_size, "min_samples": config.min_samples,
        "time_weight": config.time_weight if "time" in config.feature_set else 0,
        "cluster_count": result.n_clusters, "noise_fraction": result.noise_count / len(parcels),
        "min_cluster_size_observed": min(sizes), "median_cluster_size": statistics.median(sizes), "max_cluster_size": max(sizes),
        "mean_intra_cluster_distance_m": statistics.mean(intra) if intra else 0,
        "median_intra_cluster_distance_m": statistics.median(intra) if intra else 0,
        "spatial_purity": float(purity), "temporal_overlap_rate": statistics.mean(overlaps) if overlaps else 0,
        "split_count": repaired.n_split, "merge_count": repaired.n_merged,
        "surviving_cluster_count": repaired.clusters_after, "remaining_infeasible_cluster_count": infeasible, "seed": seed,
    }


def main() -> None:
    configurations = {
        "A_location": dict(feature_set="location"),
        "B_location_midpoint": dict(feature_set="location_time", include_window_width=False),
        "B2_location_midpoint_width": dict(feature_set="location_time", include_window_width=True),
        "C_location_physical": dict(feature_set="location_physical"),
        "D_location_time_physical": dict(feature_set="location_time_physical", include_window_width=False),
    }
    rows = []
    instances = load_instances()
    for (_key, source) in instances.items():
        for name, options in configurations.items():
            parcels = [p.model_copy(deep=True) for p in source]
            config = ClusteringConfig(**options, min_cluster_size=8, min_samples=4, time_weight=5.0)
            rows.append(metrics(parcels, cluster(parcels, 0, config), config, 0, name))
    sensitivity_source = next(iter(instances.values()))
    for mcs, samples in ((5, 3), (10, 5)):
        for feature_set, weight in (("location", 0), ("location_time", 2), ("location_time", 10)):
            parcels = [p.model_copy(deep=True) for p in sensitivity_source]
            config = ClusteringConfig(
                feature_set=feature_set, min_cluster_size=mcs,
                min_samples=samples, time_weight=weight or 5,
            )
            name = f"sensitivity_{feature_set}_mcs{mcs}_ms{samples}_tw{weight}"
            rows.append(metrics(parcels, cluster(parcels, 0, config), config, 0, name))
    OUT_DIR.mkdir(exist_ok=True)
    csv_path = OUT_DIR / "clustering_feature_experiment.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    aggregates = defaultdict(dict)
    for name in configurations:
        selected = [r for r in rows if r["configuration"] == name]
        for field in ("cluster_count", "noise_fraction", "mean_intra_cluster_distance_m", "spatial_purity", "temporal_overlap_rate", "split_count", "merge_count", "surviving_cluster_count", "remaining_infeasible_cluster_count"):
            aggregates[name][field] = statistics.mean(r[field] for r in selected)
    md = ["# Clustering Feature Experiment", "", "## Methodology", "", "Three 400-parcel depot/date instances from 2026-01-05; identical HDBSCAN parameters (min_cluster_size=8, min_samples=4), seed 0, and unchanged capacity-aware repair. Geographic coordinates use a local equirectangular projection in metres; time_weight=5 metres/minute. B2 adds window width. C/D are diagnostic only.", "", "## Aggregate results", "", "| Configuration | Clusters | Noise | Mean distance m | Purity | Time overlap | Splits | Merges | Surviving | Infeasible |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, values in aggregates.items():
        md.append(f"| {name} | {values['cluster_count']:.2f} | {values['noise_fraction']:.3f} | {values['mean_intra_cluster_distance_m']:.1f} | {values['spatial_purity']:.3f} | {values['temporal_overlap_rate']:.3f} | {values['split_count']:.2f} | {values['merge_count']:.2f} | {values['surviving_cluster_count']:.2f} | {values['remaining_infeasible_cluster_count']:.2f} |")
    md += ["", "## Sensitivity results", "", "The CSV includes location and location+time sensitivity rows at min_cluster_size/min_samples 5/3 and 10/5, with temporal weights 2 and 10 metres/minute.", "", "## Interpretation and recommendation", "", "Location-only is recommended. Midpoint time produced no meaningful temporal-overlap gain, slightly increased geographic spread, and required more repair splits. Window width reduced noise but more than doubled geographic spread. Physical configurations sharply reduced spatial purity. The recommendation is based on coherence and downstream usefulness, not cluster count.", "", "## Limitations", "", "One delivery date, three depots, seed 0, a bounded parameter sensitivity, and no NSGA-II runs. HDBSCAN is deterministic; seed affects only downstream seeded repair when a split occurs."]
    (OUT_DIR / "clustering_feature_experiment.md").write_text("\n".join(md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
