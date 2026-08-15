from app.routing.distance_matrix import nearest_neighbor_distance_km

def estimate_route_distance(depot_lat, depot_lon, parcels):
    points = [(p.latitude, p.longitude) for p in parcels]
    return nearest_neighbor_distance_km(depot_lat, depot_lon, points)
