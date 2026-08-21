"""Capacity-only ceiling and physically placed greedy reference."""
from dataclasses import dataclass
from itertools import combinations_with_replacement

from app.optimization.placement import attempt_placement


@dataclass
class UtilizationCeiling:
    utilization: float
    fleet: list[str]
    total_capacity_kg: float
    total_capacity_m3: float


@dataclass
class GreedyUtilizationReference(UtilizationCeiling):
    vehicle_loads: list[list[str]]


def compute_utilization_ceiling(weight, volume, catalog, *, max_exhaustive_fleet_size=6):
    if not catalog:
        raise ValueError("A non-empty catalog is required.")
    best = None
    for size in range(1, max_exhaustive_fleet_size + 1):
        for indices in combinations_with_replacement(range(len(catalog)), size):
            kg = sum(catalog[i].capacity_kg for i in indices)
            m3 = sum(catalog[i].capacity_m3 for i in indices)
            if kg >= weight and m3 >= volume:
                util = max(weight / kg, volume / m3)
                if best is None or util > best.utilization:
                    best = UtilizationCeiling(util, [catalog[i].code for i in indices], kg, m3)
    if best:
        return best
    largest = max(catalog, key=lambda v: (v.capacity_kg, v.capacity_m3))
    count = max(1, int(max(weight / largest.capacity_kg, volume / largest.capacity_m3)) + 1)
    return UtilizationCeiling(max(weight / (count * largest.capacity_kg), volume / (count * largest.capacity_m3)), [largest.code] * count, count * largest.capacity_kg, count * largest.capacity_m3)


def compute_utilization_greedy_reference(parcels, catalog, *, enforce_weight_order=False):
    ordered = sorted(parcels, key=lambda p: p.parcel_id)
    best = None
    for vehicle in catalog:
        loads, current, valid = [], [], True
        for parcel in ordered:
            candidate = current + [parcel]
            fits = (vehicle.max_parcels is None or len(candidate) <= vehicle.max_parcels) and sum(p.weight_kg for p in candidate) <= vehicle.capacity_kg and sum(p.volume_m3 for p in candidate) <= vehicle.capacity_m3
            if fits and attempt_placement(candidate, vehicle, enforce_weight_order=enforce_weight_order) is not None:
                current = candidate
            elif current and attempt_placement([parcel], vehicle, enforce_weight_order=enforce_weight_order) is not None:
                loads.append(current); current = [parcel]
            else:
                valid = False; break
        if not valid:
            continue
        if current: loads.append(current)
        kg, m3 = len(loads) * vehicle.capacity_kg, len(loads) * vehicle.capacity_m3
        util = max(sum(p.weight_kg for p in ordered) / kg, sum(p.volume_m3 for p in ordered) / m3)
        result = GreedyUtilizationReference(util, [vehicle.code] * len(loads), kg, m3, [[p.parcel_id for p in load] for load in loads])
        if best is None or util > best.utilization: best = result
    if best is None:
        raise ValueError("No catalog vehicle can physically place every parcel.")
    return best
