"""K-Means baseline clustering.

Satisfies SO5 (currently zero in the pre-remediation codebase): the
comparison arm the dissertation's central claim is measured against.
Shares `clustering_common`'s feature pipeline and planning-instance scoping
with HDBSCAN so the two methods are compared on identical inputs, behind
the same `cluster(parcels, seed, config) -> ClusterResult` interface.
"""
import math
import time

from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from app.models.parcel import Parcel
from app.services.clustering_common import ClusterResult, ClusteringConfig, build_feature_matrix


def _select_k(parcels: list[Parcel], X, config: ClusteringConfig, seed: int) -> int:
    """k = ceil(total_volume / mean_vehicle_capacity_m3) as a capacity-
    derived starting estimate, refined by silhouette score over
    [k_est-2, k_est+2]. `mean_vehicle_capacity_m3` must come from the
    caller (sourced from vehicle_type_catalog) — this module holds no
    vehicle capacity literal."""
    if config.mean_vehicle_capacity_m3 is None or config.mean_vehicle_capacity_m3 <= 0:
        raise ValueError(
            "ClusteringConfig.mean_vehicle_capacity_m3 must be set (from the vehicle "
            "type catalog) to select k for the K-Means baseline."
        )

    total_volume = sum(p.volume_m3 for p in parcels)
    k_est = max(1, math.ceil(total_volume / config.mean_vehicle_capacity_m3))

    n = len(parcels)
    candidates = sorted({k for k in range(k_est - 2, k_est + 3) if 2 <= k < n})
    if not candidates:
        return max(1, min(k_est, n - 1)) if n > 1 else 1

    best_k, best_score = candidates[0], -1.0
    for k in candidates:
        labels = KMeans(n_clusters=k, random_state=seed, n_init=10).fit_predict(X)
        if len(set(labels)) < 2:
            continue
        score = silhouette_score(X, labels)
        if score > best_score:
            best_score, best_k = score, k
    return best_k


def cluster(parcels: list[Parcel], seed: int, config: ClusteringConfig | None = None) -> ClusterResult:
    config = config or ClusteringConfig()
    if len(parcels) < 2:
        raise ValueError("At least 2 parcels are required for K-Means clustering.")

    t0 = time.perf_counter()
    X, scaler = build_feature_matrix(parcels, config)
    k = _select_k(parcels, X, config, seed)

    model = KMeans(n_clusters=k, random_state=seed, n_init=10)
    labels = model.fit_predict(X)

    for parcel, label in zip(parcels, labels):
        parcel.cluster_id = int(label)
        parcel.cluster_probability = 1.0
        parcel.is_noise = False

    runtime = time.perf_counter() - t0
    return ClusterResult(
        labels=labels,
        n_clusters=k,
        noise_count=0,  # K-Means has no noise concept
        runtime_seconds=runtime,
        method="kmeans",
        metadata={"seed": seed, "k": k, "model": model, "scaler": scaler},
    )
