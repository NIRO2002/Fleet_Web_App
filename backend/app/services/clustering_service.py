"""HDBSCAN clustering.

Satisfies SO1/SO2. Fixes the scaling defect (fixed-constant division let
geography dominate 91% of squared Euclidean distance by accident) with an
explicit metric projection + StandardScaler + documented feature weights,
scopes every run to one (depot_id, delivery_date) planning instance, and
resolves HDBSCAN noise (-1) explicitly instead of storing it as a
pseudo-cluster. See app/services/clustering_common.py for the shared
feature pipeline this shares with the K-Means baseline.
"""
import time
from pathlib import Path

import hdbscan
import joblib

from app.core.config import settings
from app.models.parcel import Parcel
from app.services.clustering_common import (
    ClusterResult,
    ClusteringConfig,
    build_feature_matrix,
    get_planning_instance,
    handle_noise,
    transform_with_scaler,
)


def cluster(parcels: list[Parcel], seed: int, config: ClusteringConfig | None = None) -> ClusterResult:
    """Same interface as `baseline_clustering.cluster` so the evaluation
    harness (Phase 5) can swap methods behind one call. `seed` is accepted
    for interface parity — HDBSCAN's own fit is deterministic given its
    inputs, so it is threaded through only for the metadata record, not
    used to seed anything internally today."""
    config = config or ClusteringConfig()
    if len(parcels) < config.min_cluster_size:
        raise ValueError(f"At least {config.min_cluster_size} parcels are required.")

    t0 = time.perf_counter()
    X, scaler = build_feature_matrix(parcels, config)

    model = hdbscan.HDBSCAN(
        min_cluster_size=config.min_cluster_size,
        min_samples=config.min_samples,
        prediction_data=True,
        metric="euclidean",
    )
    raw_labels = model.fit_predict(X)
    noise_count = int((raw_labels == -1).sum())

    final_labels = handle_noise(parcels, raw_labels, config)

    for parcel, label, probability in zip(parcels, final_labels, model.probabilities_):
        parcel.cluster_id = int(label)
        parcel.cluster_probability = float(probability)

    runtime = time.perf_counter() - t0
    return ClusterResult(
        labels=final_labels,
        n_clusters=len(set(final_labels.tolist())),
        noise_count=noise_count,
        runtime_seconds=runtime,
        method="hdbscan",
        metadata={"seed": seed, "model": model, "scaler": scaler},
    )


def _model_path(depot_id: str, delivery_date) -> Path:
    model_dir = Path(settings.model_dir)
    model_dir.mkdir(exist_ok=True)
    return model_dir / f"hdbscan_{depot_id}_{delivery_date}.joblib"


async def train_hdbscan(
    depot_id: str,
    delivery_date,
    seed: int = 0,
    config: ClusteringConfig | None = None,
):
    """DB- and persistence-aware wrapper around `cluster()`, scoped to one
    planning instance. Persists the fitted HDBSCAN model *and* the scaler
    it was fit with, so `predict_cluster` transforms new parcels
    consistently instead of re-fitting a scaler on a single row."""
    parcels = await get_planning_instance(depot_id, delivery_date)
    config = config or ClusteringConfig()
    result = cluster(parcels, seed, config)
    if parcels:
        await Parcel.get_motor_collection().bulk_write([
            __import__("pymongo").UpdateOne({"parcel_id": p.parcel_id}, {"$set": {"cluster_id": p.cluster_id, "cluster_probability": p.cluster_probability, "is_noise": p.is_noise}})
            for p in parcels
        ])

    joblib.dump(
        {"model": result.metadata["model"], "scaler": result.metadata["scaler"], "config": config},
        _model_path(depot_id, delivery_date),
    )
    return result, parcels


def predict_cluster(payload, depot_id: str, delivery_date):
    path = _model_path(depot_id, delivery_date)
    if not path.exists():
        raise FileNotFoundError(
            f"No HDBSCAN model trained for depot_id={depot_id!r}, delivery_date={delivery_date!r}."
        )

    bundle = joblib.load(path)
    model, scaler, config = bundle["model"], bundle["scaler"], bundle["config"]

    temp = type("ParcelLike", (), payload.model_dump())()
    X = transform_with_scaler([temp], scaler, config)
    labels, strengths = hdbscan.approximate_predict(model, X)
    label = int(labels[0])
    return {
        "cluster_id": label if label >= 0 else None,
        "cluster_probability": float(strengths[0]),
        "status": "ASSIGNED" if label >= 0 else "UNASSIGNED",
    }


async def cluster_summary(depot_id: str, delivery_date) -> dict:
    rows = await Parcel.find({"depot_id": depot_id, "delivery_date": delivery_date}).to_list()
    summary: dict[str, int] = {}
    for row in rows:
        cluster_id = row.cluster_id
        key = str(cluster_id)
        summary[key] = summary.get(key, 0) + 1
    return summary
