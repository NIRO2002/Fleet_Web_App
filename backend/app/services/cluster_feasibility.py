"""Single source of truth for placement-aware cluster/vehicle feasibility."""
from dataclasses import dataclass
import numpy as np

from app.core.config import settings
from app.optimization.placement import attempt_placement
from app.services.clustering_common import project_to_metric
from app.utils_time import minutes


@dataclass(frozen=True)
class FeasibilityResult:
    feasible: bool
    reason: str | None = None
    temporal_rejected: bool = False


def fits_some_vehicle_details(parcels, vehicle_catalog, config=None,
                              depot_lat=settings.depot_latitude, depot_lon=settings.depot_longitude):
    if not vehicle_catalog:
        return FeasibilityResult(False, "NO_FITTING_VEHICLE")
    enforce_temporal = getattr(config, "enforce_temporal_feasibility", True)
    service_minutes = getattr(config, "service_time_minutes", 4.0)
    total_weight = sum(p.weight_kg for p in parcels)
    total_volume = sum(p.volume_m3 for p in parcels)
    longest_side = max((max(p.length_cm or 0, p.width_cm or 0, p.height_cm or 0) for p in parcels), default=0)
    temporal_rejected = False
    capacity_candidate = placement_candidate = False
    if enforce_temporal and len(parcels) > 1:
        starts = [minutes(p.time_window_start) for p in parcels]
        ends = [minutes(p.time_window_end) for p in parcels]
        span = max(ends) - min(starts)
        coords = project_to_metric(parcels, depot_lat, depot_lon)
        first = int(np.argmax(np.linalg.norm(coords - coords[0], axis=1)))
        diameter = float(np.max(np.linalg.norm(coords - coords[first], axis=1)))
    for vehicle in vehicle_catalog:
        if total_weight > vehicle.capacity_kg or total_volume > vehicle.capacity_m3: continue
        if vehicle.max_parcels is not None and len(parcels) > vehicle.max_parcels: continue
        if longest_side > max(vehicle.cargo_length_cm, vehicle.cargo_width_cm, vehicle.cargo_height_cm): continue
        capacity_candidate = True
        if enforce_temporal and len(parcels) > 1:
            if len(parcels) * service_minutes + diameter / max(vehicle.avg_speed_kmh, 1e-6) * 60 > span:
                temporal_rejected = True
                continue
        placement_candidate = True
        if attempt_placement(parcels, vehicle, collect_exceptions=False) is not None:
            return FeasibilityResult(True, temporal_rejected=temporal_rejected)
    reason = "TEMPORALLY_INFEASIBLE" if temporal_rejected and not placement_candidate else (
        "PLACEMENT_INFEASIBLE" if capacity_candidate else "NO_FITTING_VEHICLE"
    )
    return FeasibilityResult(False, reason, temporal_rejected)


def fits_some_vehicle(parcels, vehicle_catalog, config=None,
                      depot_lat=settings.depot_latitude, depot_lon=settings.depot_longitude):
    return fits_some_vehicle_details(parcels, vehicle_catalog, config, depot_lat, depot_lon).feasible
