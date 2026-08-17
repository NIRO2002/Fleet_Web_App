"""Shared clustering primitives.

Satisfies SO1/SO2/SO5: a single feature-construction and planning-instance
pipeline shared by HDBSCAN (`clustering_service.py`) and the K-Means
baseline (`baseline_clustering.py`), so the two methods are compared on
identical inputs and the evaluation harness (Phase 5) can swap one for the
other behind the same `cluster(parcels, seed, config)` interface.
"""
from dataclasses import dataclass, field
from math import cos, radians
from typing import Literal

import numpy as np
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.parcel import Parcel
from app.utils_time import minutes

EARTH_RADIUS_KM = 6371.0088

# Ordinal urgency proxy derived from Parcel.priority_level. A deliberate,
# documented modelling choice (not in the original spec's literal field
# list) standing in for the "urgency" feature block.
PRIORITY_SCORE = {"standard": 0.0, "next_day": 1.0, "express": 2.0, "same_day": 3.0}


@dataclass
class ClusteringConfig:
    depot_lat: float = settings.depot_latitude
    depot_lon: float = settings.depot_longitude

    min_cluster_size: int = settings.hdbscan_min_cluster_size
    min_samples: int = settings.hdbscan_min_samples

    # Applied to the standardised feature blocks *after* scaling — spatial
    # dominance is now a deliberate, tunable choice, not an artifact of
    # unequal raw-unit scaling (the defect this replaces; see
    # docs/DESIGN_DECISIONS.md).
    feature_weights: dict = field(
        default_factory=lambda: {"spatial": 1.0, "time_window": 0.5, "urgency": 0.3}
    )

    noise_strategy: Literal["nearest_cluster", "singleton"] = "nearest_cluster"
    noise_max_assign_km: float = 3.0

    # Required only by the K-Means baseline's k-selection (SO5). Left
    # unset here deliberately — app/services/ must never contain a vehicle
    # capacity literal, so callers derive it from the vehicle_type_catalog
    # table (see vehicle_catalog_service) and pass it in explicitly.
    mean_vehicle_capacity_m3: float | None = None


@dataclass
class ClusterResult:
    labels: np.ndarray
    n_clusters: int
    noise_count: int
    runtime_seconds: float
    method: str
    metadata: dict = field(default_factory=dict)


def project_to_metric(parcels: list, depot_lat: float, depot_lon: float) -> np.ndarray:
    """Equirectangular projection around the depot, in km. Removes the
    lat/lng scale asymmetry (1 deg lat != 1 deg lng) properly instead of
    dividing by an arbitrary constant."""
    lat0 = radians(depot_lat)
    cos_lat0 = cos(lat0)
    out = [
        (
            EARTH_RADIUS_KM * radians(p.longitude - depot_lon) * cos_lat0,
            EARTH_RADIUS_KM * radians(p.latitude - depot_lat),
        )
        for p in parcels
    ]
    return np.asarray(out, dtype=float)


def _time_window_features(parcels: list) -> np.ndarray:
    """Window midpoint and width in minutes — cyclical/interval features,
    not raw start/end, so two windows that both center on midday but have
    different widths are treated as similar rather than as unrelated raw
    numbers."""
    out = []
    for p in parcels:
        start = minutes(p.time_window_start)
        end = minutes(p.time_window_end)
        out.append(((start + end) / 2.0, max(0, end - start)))
    return np.asarray(out, dtype=float)


def _urgency_features(parcels: list) -> np.ndarray:
    return np.asarray(
        [[PRIORITY_SCORE.get(getattr(p, "priority_level", "standard"), 0.0)] for p in parcels],
        dtype=float,
    )


def _weight_vector(feature_weights: dict) -> np.ndarray:
    return np.array(
        [
            feature_weights["spatial"],
            feature_weights["spatial"],
            feature_weights["time_window"],
            feature_weights["time_window"],
            feature_weights["urgency"],
        ]
    )


def raw_feature_matrix(parcels: list, depot_lat: float, depot_lon: float) -> np.ndarray:
    """[x_km, y_km, window_midpoint_min, window_width_min, urgency_score].
    `fragile` is intentionally excluded — it is a handling constraint
    enforced by the NSGA-II assignment problem (Phase 3), not a spatial
    similarity signal."""
    spatial = project_to_metric(parcels, depot_lat, depot_lon)
    time_features = _time_window_features(parcels)
    urgency = _urgency_features(parcels)
    return np.hstack([spatial, time_features, urgency])


def build_feature_matrix(
    parcels: list, config: ClusteringConfig
) -> tuple[np.ndarray, StandardScaler]:
    raw = raw_feature_matrix(parcels, config.depot_lat, config.depot_lon)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(raw)
    weighted = scaled * _weight_vector(config.feature_weights)
    return weighted, scaler


def transform_with_scaler(
    parcels: list, scaler: StandardScaler, config: ClusteringConfig
) -> np.ndarray:
    """Apply an already-fitted scaler (e.g. at single-parcel prediction
    time) instead of refitting on one row."""
    raw = raw_feature_matrix(parcels, config.depot_lat, config.depot_lon)
    scaled = scaler.transform(raw)
    return scaled * _weight_vector(config.feature_weights)


def get_planning_instance(
    db: Session, depot_id: str, delivery_date, *, include_carryover: bool = True
) -> list[Parcel]:
    """The only sanctioned way to load parcels for clustering/optimization —
    always scoped to one (depot_id, delivery_date) instance. Replaces the
    old `db.query(Parcel).all()` full-table scan.

    Fix Pass 2 item C -- the "previous day / leftover parcels" slice of the
    descoped Target 5: parcels eligible for planning on
    (depot_id, delivery_date) are every PENDING parcel already dated for
    that day, plus -- when `include_carryover` -- parcels from *earlier*
    dates at the same depot that are still PENDING or FAILED (never
    delivered or already claimed by another plan). Carried-over parcels get
    `carried_over_from_date` set to their original `delivery_date` and
    `delivery_date` moved forward to the target date. Their time windows are
    left untouched -- rescheduling a customer's delivery window is a
    customer-facing decision this system does not make, so a now-unreachable
    window shows up honestly as a compliance cost (objective f3) instead of
    being silently rewritten."""
    same_day = (
        db.query(Parcel)
        .filter(
            Parcel.depot_id == depot_id,
            Parcel.delivery_date == delivery_date,
            Parcel.status == "PENDING",
        )
        .all()
    )

    carryover: list[Parcel] = []
    if include_carryover:
        carryover = (
            db.query(Parcel)
            .filter(
                Parcel.depot_id == depot_id,
                Parcel.delivery_date < delivery_date,
                Parcel.status.in_(["PENDING", "FAILED"]),
            )
            .all()
        )
        for parcel in carryover:
            parcel.carried_over_from_date = parcel.delivery_date
            parcel.delivery_date = delivery_date

    return sorted(same_day + carryover, key=lambda p: p.parcel_id)


def handle_noise(
    parcels: list[Parcel],
    labels: np.ndarray,
    config: ClusteringConfig,
) -> np.ndarray:
    """HDBSCAN's -1 label must never become a pseudo-cluster of unrelated
    outliers. Reassigns each noise point to its nearest real-cluster
    centroid if within `noise_max_assign_km`, else gives it its own
    singleton cluster. Records the *original* label on `Parcel.is_noise` so
    the noise rate can be reported honestly even after reassignment."""
    labels = np.asarray(labels, dtype=int)
    noise_mask = labels == -1
    for parcel, was_noise in zip(parcels, noise_mask):
        parcel.is_noise = bool(was_noise)

    if not noise_mask.any():
        return labels

    coords = project_to_metric(parcels, config.depot_lat, config.depot_lon)
    real_ids = sorted(set(labels[~noise_mask].tolist()))
    new_labels = labels.copy()
    centroids = {lbl: coords[labels == lbl].mean(axis=0) for lbl in real_ids}
    next_singleton_id = (max(real_ids) + 1) if real_ids else 0

    for i in np.where(noise_mask)[0]:
        assigned = False
        if config.noise_strategy == "nearest_cluster" and centroids:
            best_lbl, best_dist = None, float("inf")
            for lbl, centroid in centroids.items():
                dist = float(np.linalg.norm(coords[i] - centroid))
                if dist < best_dist:
                    best_dist, best_lbl = dist, lbl
            if best_dist <= config.noise_max_assign_km:
                new_labels[i] = best_lbl
                assigned = True
        if not assigned:
            new_labels[i] = next_singleton_id
            next_singleton_id += 1

    return new_labels
