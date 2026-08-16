from math import radians, sin, cos, sqrt, atan2

EARTH_RADIUS_KM = 6371.0088

def haversine_km(lat1, lon1, lat2, lon2):
    p1 = radians(lat1)
    p2 = radians(lat2)
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(p1) * cos(p2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * atan2(sqrt(a), sqrt(1 - a))

def nearest_neighbor_tour(depot_lat, depot_lon, points):
    """Nearest-neighbour visiting order starting and ending at the depot.

    Returns `(order, total_distance_km)` where `order` is a list of indices
    into `points` in visiting order (1st stop first). This is a
    cost-*estimation* tour used by the optimizer (Phase 3 objective f2 and
    the delivery/load sequencing in Phase 3.4/3.5) — not a routing engine.
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
    that don't need the visiting order — delegates to `nearest_neighbor_tour`."""
    return nearest_neighbor_tour(depot_lat, depot_lon, points)[1]
