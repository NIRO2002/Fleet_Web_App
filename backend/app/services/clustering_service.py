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
from pymongo import UpdateOne

from app.core.config import settings
from app.db.bson import to_bson_safe
from app.models.parcel import Parcel
from app.services.capacity_aware_clustering import RepairConfig, RepairedClusters, group_by_cluster, repair_clusters
from app.services.clustering_common import (
    ClusterResult,
    ClusteringConfig,
    build_feature_matrix,
    get_planning_instance,
    handle_noise,
    transform_with_scaler,
)
from app.services.vehicle_catalog_service import list_available_types


def _planning_persistence_fields(parcel, fields: dict) -> dict:
    """Add a carryover's date transition at the clustering commit boundary.

    get_planning_instance deliberately returns detached forwarded copies. Once
    clustering is committed, the stored document must describe the exact
    planning instance whose cluster assignment is being persisted.
    """
    if getattr(parcel, "carried_over_from_date", None) is not None:
        fields.update({
            "carried_over_from_date": parcel.carried_over_from_date,
            "delivery_date": parcel.delivery_date,
        })
    return to_bson_safe(fields)


def cluster(parcels: list[Parcel], seed: int, config: ClusteringConfig | None = None) -> ClusterResult:
    """Same interface as `baseline_clustering.cluster` so the evaluation
    harness (Phase 5) can swap methods behind one call. `seed` is accepted
    for interface parity - HDBSCAN's own fit is deterministic given its
    inputs, so it is threaded through only for the metadata record, not
    used to seed anything internally today."""
    config = config or ClusteringConfig()
    planning_keys = {(p.depot_id, p.delivery_date) for p in parcels}
    if len(planning_keys) > 1:
        raise ValueError("HDBSCAN input must contain exactly one depot/date planning instance.")
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
        # -1.0 is the documented sentinel for a point HDBSCAN originally
        # labelled noise, including points geographically reassigned later.
        parcel.cluster_probability = -1.0 if parcel.is_noise else float(probability)

    runtime = time.perf_counter() - t0
    return ClusterResult(
        labels=final_labels,
        n_clusters=len({label for label in raw_labels.tolist() if label >= 0}),
        noise_count=noise_count,
        runtime_seconds=runtime,
        method="hdbscan",
        metadata={"seed": seed, "model": model, "scaler": scaler},
        post_noise_cluster_count=len({label for label in final_labels.tolist() if label >= 0}),
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
    dataset_id: str | None = None,
):
    """DB- and persistence-aware wrapper around `cluster()`, scoped to one
    planning instance. Persists the fitted HDBSCAN model *and* the scaler
    it was fit with, so `predict_cluster` transforms new parcels
    consistently instead of re-fitting a scaler on a single row.

    Per-instance labels start at 0 -- this is the natural output of
    clustering, not a defect. Callers must resolve cluster_id together with
    (depot_id, delivery_date), never on cluster_id alone (see
    app/api/v1/optimization.py); an offset here only papered over that
    missing scope instead of fixing it. See docs/DESIGN_DECISIONS.md."""
    parcels = await get_planning_instance(
        depot_id,
        delivery_date,
        dataset_id=dataset_id,
    )
    config = config or ClusteringConfig()
    result = cluster(parcels, seed, config)
    if parcels:
        await Parcel.get_motor_collection().bulk_write([
            UpdateOne(
                {"parcel_id": p.parcel_id},
                {"$set": _planning_persistence_fields(p, {
                    "cluster_id": p.cluster_id,
                    "cluster_probability": p.cluster_probability,
                    "is_noise": p.is_noise,
                })},
            )
            for p in parcels
        ])

    joblib.dump(
        {
            "model": result.metadata["model"],
            "scaler": result.metadata["scaler"],
            "config": config,
        },
        _model_path(depot_id, delivery_date),
    )
    return result, parcels


async def repair_planning_instance(
    depot_id: str,
    parcels: list[Parcel],
    *,
    depot_lat: float,
    depot_lon: float,
    seed: int = 0,
) -> RepairedClusters | None:
    """Capacity-aware repair (split oversize / merge undersize clusters
    against `vehicle_type_catalog`) on a just-trained instance -- the same
    HDBSCAN -> repair -> NSGA-II pipeline app/evaluation/harness.py
    exercises for evaluation, reusing its exact `repair_clusters`/
    `RepairConfig`/`group_by_cluster` rather than a forked copy, now wired
    into the live training path instead of only the offline harness.

    Noise remains cluster_id=-1 and bypasses repair entirely. Persists the
    repaired cluster_id back to Parcel. A real cluster repair marks
    infeasible (no catalog vehicle can carry it, even split/merged) is
    persisted as cluster_id=-1, not as an ordinary optimizable cluster --
    repair must never launder an unroutable parcel into something
    /optimization/run will silently accept (see the noise-handling
    guarantee in api/v1/optimization.py and GET /parcels/clustering/unassigned).

    Returns None (repair skipped, not applied) if the depot has no active
    vehicle types yet -- vehicle catalog setup and HDBSCAN training are
    independent prerequisites, so an empty catalog should not hard-fail
    training itself."""
    catalog = await list_available_types(depot_id)
    if not catalog:
        return None

    clusters = group_by_cluster(parcels)
    repaired = repair_clusters(clusters, catalog, RepairConfig(), depot_lat, depot_lon, seed=seed)

    updates = []
    for cluster_id, members in repaired.clusters.items():
        feasible = repaired.cluster_status[cluster_id]["feasible"]
        persisted_id = cluster_id if feasible else -1
        for parcel in members:
            parcel.cluster_id = persisted_id
            updates.append(UpdateOne(
                {"parcel_id": parcel.parcel_id},
                {"$set": _planning_persistence_fields(parcel, {"cluster_id": persisted_id})},
            ))
    if updates:
        await Parcel.get_motor_collection().bulk_write(updates)

    return repaired


def predict_cluster(payload, depot_id: str, delivery_date):
    """Returns cluster_id=None/status=UNASSIGNED unconditionally -- never a
    raw HDBSCAN label. The joblib bundle holds only the fitted HDBSCAN
    model, not the capacity-aware repair outcome
    (app/services/capacity_aware_clustering.py) that runs afterward and is
    what actually determines a parcel's *persisted* cluster_id, so a raw
    `approximate_predict` label does not correspond to any real, currently
    persisted cluster. Translating it would require a raw_label ->
    repaired_cluster_id map, but that map is only well-defined for
    merge-origin clusters -- a split partitions one raw cluster's *points*
    by a KMeans boundary that is not reproducible from a label alone, so
    guessing which child a new point landed in could return a real-looking
    but wrong cluster_id. See docs/DESIGN_DECISIONS.md's "predict_cluster
    cannot return a post-repair cluster_id" entry for the full reasoning
    and the rejected alternative.

    `cluster_probability` (HDBSCAN's own membership-strength metric) is
    still returned -- it says how confidently this point fits the trained
    density model at all, which stays meaningful independent of which
    specific (possibly repair-renumbered) cluster it would land in."""
    path = _model_path(depot_id, delivery_date)
    if not path.exists():
        raise FileNotFoundError(
            f"No HDBSCAN model trained for depot_id={depot_id!r}, delivery_date={delivery_date!r}."
        )

    bundle = joblib.load(path)
    model, scaler, config = bundle["model"], bundle["scaler"], bundle["config"]

    temp = type("ParcelLike", (), payload.model_dump())()
    X = transform_with_scaler([temp], scaler, config)
    _labels, strengths = hdbscan.approximate_predict(model, X)
    return {
        "cluster_id": None,
        "cluster_probability": float(strengths[0]),
        "status": "UNASSIGNED",
        "reason": "prediction unavailable after capacity repair",
    }


async def cluster_summary(depot_id: str, delivery_date, dataset_id: str | None = None) -> dict:
    filters = (
        {"dataset_id": dataset_id}
        if dataset_id is not None
        else {"depot_id": depot_id, "delivery_date": delivery_date}
    )
    rows = await Parcel.find(filters).to_list()
    summary: dict[str, int] = {}
    for row in rows:
        cluster_id = row.cluster_id
        key = str(cluster_id)
        summary[key] = summary.get(key, 0) + 1
    return summary
