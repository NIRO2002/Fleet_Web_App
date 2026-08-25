from math import radians, sin, cos, sqrt, atan2

import numpy as np

EARTH_RADIUS_KM = 6371.0088

def haversine_km(lat1, lon1, lat2, lon2):
    p1 = radians(lat1)
    p2 = radians(lat2)
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(p1) * cos(p2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * atan2(sqrt(a), sqrt(1 - a))


def haversine_matrix_km(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Vectorised pairwise haversine distance matrix (n x n), for the GA's
    hot path (Fix Pass 2 B.1) where the same n points get a tour computed
    against them repeatedly across a whole run -- replaces a per-call Python
    loop of `haversine_km` with one `numpy` broadcast."""
    lat_r = np.radians(lats)
    lon_r = np.radians(lons)
    dlat = lat_r[:, None] - lat_r[None, :]
    dlon = lon_r[:, None] - lon_r[None, :]
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat_r[:, None]) * np.cos(lat_r[None, :]) * np.sin(dlon / 2.0) ** 2
    return 2 * EARTH_RADIUS_KM * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def haversine_vector_km(depot_lat: float, depot_lon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Vectorised distance from one fixed point (the depot) to every point
    in `lats`/`lons` -- the depot-distance counterpart to
    `haversine_matrix_km`."""
    lat0, lon0 = radians(depot_lat), radians(depot_lon)
    lat_r = np.radians(lats)
    lon_r = np.radians(lons)
    dlat = lat_r - lat0
    dlon = lon_r - lon0
    a = np.sin(dlat / 2.0) ** 2 + cos(lat0) * np.cos(lat_r) * np.sin(dlon / 2.0) ** 2
    return 2 * EARTH_RADIUS_KM * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def nearest_neighbor_tour_from_matrix(
    depot_dist: np.ndarray, matrix: np.ndarray, indices: list[int]
) -> tuple[list[int], float]:
    """Same nearest-neighbour tour as `nearest_neighbor_tour`, but reading
    distances out of a precomputed full-instance matrix (Fix Pass 2 B.1)
    instead of calling `haversine_km` in a Python loop, and picking the next
    stop with `np.argmin` over a masked row instead of Python's `min()`
    (measured faster than an equivalent plain-Python-list version at the
    slot sizes this runs at -- numpy's per-call overhead is real but the
    masked-argmin approach still won). `indices` are positions into the
    full instance (rows/columns of `matrix`/`depot_dist`), not into a
    slot-local list."""
    if not indices:
        return [], 0.0
    idx = np.asarray(indices)
    remaining = np.ones(len(idx), dtype=bool)
    current_row = depot_dist[idx]
    order: list[int] = []
    total = 0.0
    for _ in range(len(idx)):
        masked = np.where(remaining, current_row, np.inf)
        nxt = int(np.argmin(masked))
        total += float(masked[nxt])
        order.append(nxt)
        remaining[nxt] = False
        current_row = matrix[idx[nxt], idx]
    total += float(depot_dist[idx[order[-1]]])
    return order, total

def nearest_neighbor_tour(depot_lat, depot_lon, points):
    """Nearest-neighbour visiting order starting and ending at the depot.

    Returns `(order, total_distance_km)` where `order` is a list of indices
    into `points` in visiting order (1st stop first). This is a
    cost-*estimation* tour used by the optimizer (Phase 3 objective f2 and
    the delivery/load sequencing in Phase 3.4/3.5) - not a routing engine.
    The downstream route-optimization module owns the real route.
    """
    if not points:
        return [], 0.0
    remaining = list(range(len(points)))
    current = (depot_lat, depot_lon)
    order = []
    total = 0.0
    while remaining:
        nxt = min(remaining, key=lambda i: haversine_km(current[0], current[1], points[i][0], points[i][1]))
        total += haversine_km(current[0], current[1], points[nxt][0], points[nxt][1])
        current = points[nxt]
        order.append(nxt)
        remaining.remove(nxt)
    total += haversine_km(current[0], current[1], depot_lat, depot_lon)
    return order, total

def nearest_neighbor_distance_km(depot_lat, depot_lon, points):
    """Total tour distance only. Kept for existing callers (`app.routing.optimizer`)
    that don't need the visiting order - delegates to `nearest_neighbor_tour`."""
    return nearest_neighbor_tour(depot_lat, depot_lon, points)[1]
