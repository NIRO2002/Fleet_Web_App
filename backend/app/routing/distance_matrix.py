from math import radians, sin, cos, sqrt, atan2

EARTH_RADIUS_KM = 6371.0088

def haversine_km(lat1, lon1, lat2, lon2):
    p1 = radians(lat1)
    p2 = radians(lat2)
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(p1) * cos(p2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * atan2(sqrt(a), sqrt(1 - a))

def nearest_neighbor_distance_km(depot_lat, depot_lon, points):
    if not points:
        return 0.0
    remaining = list(points)
    current = (depot_lat, depot_lon)
    total = 0.0
    while remaining:
        nxt = min(remaining, key=lambda p: haversine_km(current[0], current[1], p[0], p[1]))
        total += haversine_km(current[0], current[1], nxt[0], nxt[1])
        current = nxt
        remaining.remove(nxt)
    return total + haversine_km(current[0], current[1], depot_lat, depot_lon)
