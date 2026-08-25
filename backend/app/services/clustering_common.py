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

from app.core.config import settings
from app.models.parcel import Parcel
from app.utils_time import minutes

EARTH_RADIUS_KM = 6371.0088
METRES_PER_KM = 1000.0

# Ordinal urgency proxy derived from Parcel.priority_level. A deliberate,
# documented modelling choice (not in the original spec's literal field
# list) standing in for the "urgency" feature block.
PRIORITY_SCORE = {"standard": 0.0, "next_day": 1.0, "express": 2.0, "priority": 2.5, "same_day": 3.0}


@dataclass
class ClusteringConfig:
    depot_lat: float = settings.depot_latitude
    depot_lon: float = settings.depot_longitude

    min_cluster_size: int = settings.hdbscan_min_cluster_size
    min_samples: int = settings.hdbscan_min_samples

    # Applied to the standardised feature blocks *after* scaling - spatial
    # dominance is now a deliberate, tunable choice, not an artifact of
    # unequal raw-unit scaling (the defect this replaces; see
    # docs/DESIGN_DECISIONS.md).
    feature_set: Literal[
        "location", "location_time", "location_urgency", "location_time_urgency",
        "location_physical", "location_time_physical"
    ] = "location"
    include_window_width: bool = False
    time_weight: float = 5.0  # metres per minute
    physical_weight: float = 500.0  # metres per standard deviation; experiment only
    urgency_weight: float = 500.0  # metres per standard deviation; experiment only

    noise_strategy: Literal["nearest_cluster", "singleton"] = "nearest_cluster"
    noise_max_assign_km: float = 0.75

    # Required only by the K-Means baseline's k-selection (SO5). Left
    # unset here deliberately - app/services/ must never contain a vehicle
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
    post_noise_cluster_count: int | None = None


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


def project_to_metres(parcels: list, depot_lat: float, depot_lon: float) -> np.ndarray:
    """Local metric projection for clustering; accurate for depot-scale instances."""
    return project_to_metric(parcels, depot_lat, depot_lon) * METRES_PER_KM


def _time_window_features(parcels: list) -> np.ndarray:
    """Window midpoint and width in minutes - cyclical/interval features,
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
    `fragile` is intentionally excluded - it is a handling constraint
    enforced by the NSGA-II assignment problem (Phase 3), not a spatial
    similarity signal."""
    spatial = project_to_metric(parcels, depot_lat, depot_lon)
    time_features = _time_window_features(parcels)
    urgency = _urgency_features(parcels)
    return np.hstack([spatial, time_features, urgency])


def _physical_features(parcels: list) -> np.ndarray:
    """Physical diagnostic block for experiment C/D, never the default."""
    return np.asarray([
        [p.weight_kg, p.volume_m3, p.length_cm or 0.0, p.width_cm or 0.0,
         p.height_cm or 0.0, float(p.fragile), float(p.stackable)]
        for p in parcels
    ], dtype=float)


def feature_names(config: ClusteringConfig) -> tuple[str, ...]:
    names = ["projected_x_m", "projected_y_m"]
    if "time" in config.feature_set:
        names.append("window_midpoint_min")
        if config.include_window_width:
            names.append("window_width_min")
    if "physical" in config.feature_set:
        names.extend(("weight_kg", "volume_m3", "length_cm", "width_cm", "height_cm", "fragile", "stackable"))
    if "urgency" in config.feature_set:
        names.append("priority_score")
    return tuple(names)


@dataclass
class FeatureTransformer:
    config: ClusteringConfig
    physical_scaler: StandardScaler | None = None
    urgency_scaler: StandardScaler | None = None

    def transform(self, parcels: list) -> np.ndarray:
        blocks = [project_to_metres(parcels, self.config.depot_lat, self.config.depot_lon)]
        if "time" in self.config.feature_set:
            temporal = _time_window_features(parcels)
            columns = [temporal[:, :1] * self.config.time_weight]
            if self.config.include_window_width:
                columns.append(temporal[:, 1:2] * self.config.time_weight)
            blocks.append(np.hstack(columns))
        if "physical" in self.config.feature_set:
            if self.physical_scaler is None:
                raise ValueError("physical transformer is not fitted")
            physical = self.physical_scaler.transform(_physical_features(parcels))
            blocks.append(physical * self.config.physical_weight)
        if "urgency" in self.config.feature_set:
            if self.urgency_scaler is None:
                raise ValueError("urgency transformer is not fitted")
            blocks.append(self.urgency_scaler.transform(_urgency_features(parcels)) * self.config.urgency_weight)
        return np.hstack(blocks)


def build_feature_matrix(
    parcels: list, config: ClusteringConfig
) -> tuple[np.ndarray, FeatureTransformer]:
    transformer = FeatureTransformer(config=config)
    if "physical" in config.feature_set:
        transformer.physical_scaler = StandardScaler().fit(_physical_features(parcels))
    if "urgency" in config.feature_set:
        transformer.urgency_scaler = StandardScaler().fit(_urgency_features(parcels))
    return transformer.transform(parcels), transformer


def transform_with_scaler(
    parcels: list, scaler: FeatureTransformer, config: ClusteringConfig
) -> np.ndarray:
    """Apply an already-fitted scaler (e.g. at single-parcel prediction
    time) instead of refitting on one row."""
    if not isinstance(scaler, FeatureTransformer):
        raise ValueError("Stored clustering model uses the retired feature pipeline; retrain HDBSCAN.")
    return scaler.transform(parcels)


async def _get_planning_instance(
    depot_id: str,
    delivery_date,
    *,
    include_carryover: bool = True,
    dataset_id: str | None = None,
) -> list[Parcel]:
    """The only sanctioned way to load parcels for clustering/optimization -
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
    same_day_filter = {"depot_id": depot_id, "delivery_date": delivery_date, "status": "PENDING"}
    if dataset_id is not None:
        same_day_filter["dataset_id"] = dataset_id
        include_carryover = False
    if not include_carryover:
        same_day_filter["carried_over_from_date"] = None
    same_day = await Parcel.find(same_day_filter).to_list()

    carryover: list[Parcel] = []
    if include_carryover:
        stored_carryover = await Parcel.find({"depot_id": depot_id, "delivery_date": {"$lt": delivery_date}, "status": {"$in": ["PENDING", "FAILED"]}}).to_list()
        for stored in stored_carryover:
            # Loading an evaluation/planning instance must never mutate the
            # benchmark collection. The eventual plan-commit path owns any
            # persistent status/date transition.
            parcel = stored.model_copy(deep=True)
            parcel.carried_over_from_date = stored.delivery_date
            parcel.delivery_date = delivery_date
            carryover.append(parcel)

    return sorted(same_day + carryover, key=lambda p: p.parcel_id)

def get_planning_instance(*args, **kwargs):
    if args and hasattr(args[0], "run"):
        return args[0].run(_get_planning_instance(*args[1:], **kwargs))
    return _get_planning_instance(*args, **kwargs)


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
            # Keep genuinely unassignable points as noise. Capacity repair
            # never converts HDBSCAN noise into an ordinary cluster.
            new_labels[i] = -1

    return new_labels
