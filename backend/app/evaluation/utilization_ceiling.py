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


@dataclass
class UtilizationCeiling:
    utilization: float
    fleet: list[str]  # catalog codes, one entry per vehicle in the best fleet found
    total_capacity_kg: float
    total_capacity_m3: float


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
