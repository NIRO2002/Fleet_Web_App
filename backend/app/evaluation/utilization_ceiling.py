"""Utilization ceiling (Fix Pass 4 item S2).

Given one instance's total weight/volume and the vehicle catalog, computes
the best achievable utilization by capacity alone -- an upper bound the
actual optimizer's result can be measured against. Exhaustive over fleet
sizes 1-6 (at most a few thousand combinations over a realistic 7-10 type
catalog -- cheap to brute force), falling back to a greedy largest-first
fill beyond 6 vehicles.

This says nothing about whether such a fleet is *reachable* by the
optimizer -- dimensional fit, time windows, and stacking aren't considered
here, only aggregate weight/volume capacity. It is a theoretical ceiling,
not a claim that the optimizer should reach it; report achieved-vs-ceiling,
never tune toward the ceiling.
"""
from dataclasses import dataclass
from itertools import combinations_with_replacement

from app.optimization.placement import attempt_placement


@dataclass
class UtilizationCeiling:
    utilization: float
    fleet: list[str]  # catalog codes, one entry per vehicle in the best fleet found
    total_capacity_kg: float
    total_capacity_m3: float


@dataclass
class PlacementAwareCeiling(UtilizationCeiling):
    """A physically attainable reference produced by actual placement.

    Unlike :class:`UtilizationCeiling`, this is not a mathematical upper
    bound. It is a conservative greedy baseline -- every reported load has
    passed the production LIFO placement routine, but the packing order is
    a single stable-ID greedy sweep, not an optimized one. A good optimizer
    is expected to beat it; a reported achieved/reference ratio above 100%
    is the expected outcome, not an error.
    """

    vehicle_loads: list[list[str]]


def compute_placement_aware_ceiling(parcels, catalog) -> PlacementAwareCeiling:
    """Pack the instance with each homogeneous fleet and keep the fullest.

    Parcels are considered in stable ID order. A vehicle is closed as soon
    as adding the next parcel makes aggregate capacity, count, dimensions,
    or the real placement routine fail. This intentionally reports an
    *attainable* reference rather than pretending that an NP-hard packing
    heuristic is a proven global upper bound.
    """
    if not catalog:
        raise ValueError("compute_placement_aware_ceiling requires a non-empty catalog.")
    ordered = sorted(parcels, key=lambda p: p.parcel_id)
    if not ordered:
        return PlacementAwareCeiling(1.0, [], 0.0, 0.0, [])

    total_weight = sum(p.weight_kg for p in ordered)
    total_volume = sum(p.volume_m3 for p in ordered)
    best = None
    for vehicle in catalog:
        loads: list[list] = []
        current: list = []
        feasible = True
        for parcel in ordered:
            candidate = current + [parcel]
            within_count = vehicle.max_parcels is None or len(candidate) <= vehicle.max_parcels
            within_weight = sum(p.weight_kg for p in candidate) <= vehicle.capacity_kg
            within_volume = sum(p.volume_m3 for p in candidate) <= vehicle.capacity_m3
            if within_count and within_weight and within_volume and attempt_placement(candidate, vehicle) is not None:
                current = candidate
                continue
            if not current or attempt_placement([parcel], vehicle) is None:
                feasible = False
                break
            loads.append(current)
            current = [parcel]
        if not feasible:
            continue
        if current:
            loads.append(current)

        cap_kg = len(loads) * vehicle.capacity_kg
        cap_m3 = len(loads) * vehicle.capacity_m3
        utilization = max(total_weight / cap_kg, total_volume / cap_m3)
        result = PlacementAwareCeiling(
            utilization=utilization,
            fleet=[vehicle.code] * len(loads),
            total_capacity_kg=cap_kg,
            total_capacity_m3=cap_m3,
            vehicle_loads=[[p.parcel_id for p in load] for load in loads],
        )
        if best is None or result.utilization > best.utilization:
            best = result

    if best is None:
        raise ValueError("No catalog vehicle can physically place every parcel in the instance.")
    return best


def compute_utilization_ceiling(
    total_weight_kg: float, total_volume_m3: float, catalog, *, max_exhaustive_fleet_size: int = 6
) -> UtilizationCeiling:
    """`catalog` is any sequence of objects with `.code`, `.capacity_kg`,
    `.capacity_m3` (a `tuple[VehicleTypeSpec, ...]` or the raw
    `VehicleTypeCatalog` ORM rows both work)."""
    if not catalog:
        raise ValueError("compute_utilization_ceiling requires a non-empty catalog.")
    if total_weight_kg <= 0 and total_volume_m3 <= 0:
        return UtilizationCeiling(utilization=1.0, fleet=[], total_capacity_kg=0.0, total_capacity_m3=0.0)

    best: UtilizationCeiling | None = None
    n = len(catalog)
    # Every fleet size 1..max_exhaustive_fleet_size is searched, not just the
    # first feasible one: catalog capacities are discrete, so a larger fleet
    # is not guaranteed to have more slack than a smaller one's best fit.
    for k in range(1, max_exhaustive_fleet_size + 1):
        for combo in combinations_with_replacement(range(n), k):
            cap_kg = sum(catalog[i].capacity_kg for i in combo)
            cap_m3 = sum(catalog[i].capacity_m3 for i in combo)
            if cap_kg < total_weight_kg or cap_m3 < total_volume_m3:
                continue
            utilization = max(
                total_weight_kg / cap_kg if cap_kg else 0.0,
                total_volume_m3 / cap_m3 if cap_m3 else 0.0,
            )
            if best is None or utilization > best.utilization:
                best = UtilizationCeiling(
                    utilization=utilization,
                    fleet=[catalog[i].code for i in combo],
                    total_capacity_kg=cap_kg,
                    total_capacity_m3=cap_m3,
                )

    if best is not None:
        return best

    # Greedy fallback beyond max_exhaustive_fleet_size: repeatedly add the
    # largest-capacity type until both dimensions are covered. Only reached
    # when the load is too large for any <=6-vehicle exhaustive combination.
    largest = max(catalog, key=lambda v: (v.capacity_kg, v.capacity_m3))
    fleet_codes: list[str] = []
    cap_kg = cap_m3 = 0.0
    while cap_kg < total_weight_kg or cap_m3 < total_volume_m3:
        fleet_codes.append(largest.code)
        cap_kg += largest.capacity_kg
        cap_m3 += largest.capacity_m3
    utilization = max(total_weight_kg / cap_kg, total_volume_m3 / cap_m3)
    return UtilizationCeiling(utilization, fleet_codes, cap_kg, cap_m3)
