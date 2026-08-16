"""NSGA-II parcel-to-vehicle-slot assignment problem (Phase 3.1-3.3).

Satisfies SO3/SO4/FR04. Replaces the pre-remediation defect: the old
`VehicleTypeNSGAProblem` had `n_var=1` (pick one vehicle *type* for the
*entire, fixed* parcel list), so distance and compliance never varied with
the decision variable and the "search" collapsed to picking the smallest
feasible box among four literal options. Here, decision variables are:

- genes `0 .. n-1`: which vehicle *slot* (0..K-1) each parcel is assigned to
- genes `n .. n+K-1`: which catalog vehicle *type* (0..T-1) each slot is

so which parcels share a vehicle, and what that vehicle is, are both
searched. `T = len(catalog)` is read from `vehicle_type_catalog` at
runtime — this module must never contain a vehicle capacity literal, and
adding a 5th catalog row must not require a code change here.
"""
import logging
import math
import statistics
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np
from pymoo.core.problem import Problem
from pymoo.core.repair import Repair
from pymoo.core.sampling import Sampling
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM
from pymoo.operators.repair.rounding import RoundingRepair
from pymoo.operators.sampling.rnd import IntegerRandomSampling
from pymoo.optimize import minimize
from sqlalchemy.orm import Session

from app.core.config import settings
from app.optimization.placement import attempt_placement
from app.routing.distance_matrix import haversine_km, nearest_neighbor_tour
from app.services.vehicle_catalog_service import VehicleCatalogCache, list_available_types
from app.utils_time import minutes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VehicleTypeSpec:
    """Immutable per-run snapshot of one `vehicle_type_catalog` row. The GA's
    inner loop reads only this — never the database — for the run's
    duration (a single round trip per run, not per evaluation)."""

    code: str
    capacity_kg: float
    capacity_m3: float
    cargo_length_cm: float
    cargo_width_cm: float
    cargo_height_cm: float
    max_parcels: int
    max_stack_layers: int
    fixed_cost: float
    cost_per_km: float
    avg_speed_kmh: float
    is_refrigerated: bool
    temp_min_celsius: float | None
    temp_max_celsius: float | None
    is_hazmat_certified: bool
    has_tail_lift: bool


def load_catalog_snapshot(
    db: Session,
    depot_id: str | None,
    delivery_date=None,
    *,
    cache: VehicleCatalogCache | None = None,
) -> tuple[VehicleTypeSpec, ...]:
    """The only way `app/optimization/` obtains vehicle data. Raises rather
    than silently falling back to a built-in default if the catalog is
    empty for this depot (spec 3.1)."""
    rows = list_available_types(db, depot_id, delivery_date, cache=cache)
    if not rows:
        raise ValueError(
            f"No active vehicle types available for depot_id={depot_id!r}. "
            "The optimizer never falls back to a built-in default catalog — "
            "seed or activate at least one row in vehicle_type_catalog."
        )
    return tuple(
        VehicleTypeSpec(
            code=r.code,
            capacity_kg=r.capacity_kg,
            capacity_m3=r.capacity_m3,
            cargo_length_cm=r.cargo_length_cm,
            cargo_width_cm=r.cargo_width_cm,
            cargo_height_cm=r.cargo_height_cm,
            max_parcels=r.max_parcels,
            max_stack_layers=r.max_stack_layers,
            fixed_cost=r.fixed_cost,
            cost_per_km=r.cost_per_km,
            avg_speed_kmh=r.avg_speed_kmh,
            is_refrigerated=r.is_refrigerated,
            temp_min_celsius=r.temp_min_celsius,
            temp_max_celsius=r.temp_max_celsius,
            is_hazmat_certified=r.is_hazmat_certified,
            has_tail_lift=r.has_tail_lift,
        )
        for r in rows
    )


@dataclass
class AssignmentConfig:
    depot_lat: float = settings.depot_latitude
    depot_lon: float = settings.depot_longitude

    # Safety cap on K (see `slot_budget`) -- raised from the old 40, and
    # `slot_budget` additionally scales this with n_parcels, since a flat
    # cap could truncate a genuinely capacity-justified K for a large
    # instance.
    max_vehicle_slots: int = 100
    # How far above the "typical vehicle" capacity-derived estimate (k_est)
    # `slot_budget` inflates K, to leave the GA room to use smaller/mixed
    # vehicle types instead of only the median-capacity one.
    slot_slack: float = 1.5

    service_time_minutes: float = 4.0
    two_person_lift_service_multiplier: float = 2.0
    # Clock time the vehicle leaves the depot. Time-window compliance
    # compares simulated *clock* time against each parcel's HH:MM window,
    # so this baseline matters — starting the simulation at minute 0
    # (midnight) would make every daytime window unreachable. Defaults from
    # `settings` so it is configurable without touching this dataclass.
    depot_departure_time: str = settings.depot_departure_time

    population: int = settings.nsga2_population
    generations: int = settings.nsga2_generations
    warm_start_count: int = 5


def slot_budget(
    parcels: list, catalog: tuple[VehicleTypeSpec, ...], config: AssignmentConfig, n_warm_clusters: int = 0
) -> int:
    """K, the number of vehicle slots *offered* to the GA — an upper bound
    on distinct slots, never a floor: the GA can legally leave slots empty
    or put every parcel in one slot, so a tighter K only means less wasted
    search space to consolidate out of, not a change to what's reachable.

    Derived from the parcels' total demand against the catalog's capacity
    range, replacing the old flat `n_parcels / min_parcels_per_vehicle`
    estimate (which didn't know the catalog even existed):

    - `k_min`: the fewest vehicles physically possible at all — total
      demand against the single *largest*-capacity catalog type.
    - `k_est`: a realistic planning estimate — total demand against a
      *typical* (median-capacity) catalog type, inflated by `slot_slack`
      to leave room for the GA to actually use smaller/mixed types instead
      of only the median one.

    Bounded above by a safety cap (`max_vehicle_slots`, scaled with
    `n_parcels` so a large instance doesn't get truncated below what its
    own demand justifies) and below by `n_warm_clusters`, so every
    warm-start cluster can seed its own slot."""
    n_parcels = len(parcels)
    if n_parcels == 0:
        return max(1, n_warm_clusters)

    total_weight = sum(p.weight_kg for p in parcels)
    total_volume = sum(p.volume_m3 for p in parcels)

    capacities_kg = sorted(v.capacity_kg for v in catalog if v.capacity_kg > 0)
    capacities_m3 = sorted(v.capacity_m3 for v in catalog if v.capacity_m3 > 0)
    if not capacities_kg or not capacities_m3:
        raise ValueError("slot_budget requires at least one catalog type with positive capacity_kg and capacity_m3.")

    largest_kg, largest_m3 = capacities_kg[-1], capacities_m3[-1]
    median_kg = statistics.median(capacities_kg)
    median_m3 = statistics.median(capacities_m3)

    k_min = math.ceil(max(total_weight / largest_kg, total_volume / largest_m3))
    k_est = math.ceil(max(total_weight / median_kg, total_volume / median_m3))

    max_slots = max(config.max_vehicle_slots, math.ceil(n_parcels / 3))
    K = min(max_slots, max(n_warm_clusters, math.ceil(k_est * config.slot_slack), k_min + 1))
    return max(1, K)


def decode(row, n: int, K: int) -> tuple[dict[int, list[int]], np.ndarray]:
    """Splits one individual's gene row into `{slot_idx: [parcel indices]}`
    (only slots that actually received a parcel) and the per-slot type
    index array."""
    row = np.asarray(row)
    slot_of_parcel = row[:n].astype(int)
    type_of_slot = row[n : n + K].astype(int)
    slots: dict[int, list[int]] = {}
    for parcel_idx, slot in enumerate(slot_of_parcel):
        slots.setdefault(int(slot), []).append(parcel_idx)
    return slots, type_of_slot


def _dimension_fits(parcel, vehicle: VehicleTypeSpec) -> bool:
    """Constraint 4: does the parcel fit the cargo bay in *some* axis
    permutation (unless `loading_orientation_fixed`, which forbids
    rotation)? Missing dimensions fall back to a volume-derived cube — by
    the time parcels reach here Phase 1's importer should have already
    imputed real ones. Whenever the dimensions are imputed (flagged by the
    importer via `dimensions_imputed`, or imputed here because the object
    has no real dimensions at all), a safety factor inflates the imputed
    side (F12): a cube is a last-resort guess, and treating it at face
    value would let a parcel that is really long and thin pass a fit check
    it cannot physically satisfy."""
    length, width, height = parcel.length_cm, parcel.width_cm, parcel.height_cm
    imputed = bool(getattr(parcel, "dimensions_imputed", False))
    if not (length and width and height):
        side = (max(parcel.volume_m3, 1e-9) * 1_000_000) ** (1 / 3)
        length = width = height = side
        imputed = True
    if imputed:
        factor = settings.imputed_dimension_safety_factor
        length, width, height = length * factor, width * factor, height * factor

    if parcel.loading_orientation_fixed:
        return length <= vehicle.cargo_length_cm and width <= vehicle.cargo_width_cm and height <= vehicle.cargo_height_cm

    dims = sorted([length, width, height], reverse=True)
    cargo = sorted([vehicle.cargo_length_cm, vehicle.cargo_width_cm, vehicle.cargo_height_cm], reverse=True)
    return all(d <= c for d, c in zip(dims, cargo))


def _hazmat_ok(parcel, vehicle: VehicleTypeSpec) -> bool:
    if not (parcel.hazardous or parcel.hazmat_class):
        return True
    return vehicle.is_hazmat_certified


def _refrigeration_ok(parcel, vehicle: VehicleTypeSpec) -> bool:
    if not parcel.requires_refrigeration:
        return True
    if not vehicle.is_refrigerated:
        return False
    if parcel.temp_min_celsius is not None and vehicle.temp_min_celsius is not None:
        if parcel.temp_min_celsius < vehicle.temp_min_celsius:
            return False
    if parcel.temp_max_celsius is not None and vehicle.temp_max_celsius is not None:
        if parcel.temp_max_celsius > vehicle.temp_max_celsius:
            return False
    return True


def schedule_time_window_compliance(
    parcels_in_delivery_order: list, vehicle: VehicleTypeSpec, config: AssignmentConfig
) -> tuple[float, list[bool], float]:
    """Replaces the deprecated pairwise-overlap metric (spec 3.2): walks the
    vehicle's actual nearest-neighbour tour, accumulating travel time from
    `avg_speed_kmh` plus a per-stop service time (doubled for
    `two_person_lift` parcels), and counts a parcel compliant only if the
    vehicle's simulated arrival falls inside its own time window — i.e.
    whether the delivery will actually be on time, not just whether two
    parcels' windows could theoretically coexist.

    A vehicle that arrives *before* a window opens waits for it rather than
    failing compliance — real vehicles do this. Waiting consumes shift time,
    so it pushes the clock forward (an early stop can still cause a later
    stop to run late) and the total is returned for the metrics layer, even
    though it is not itself an objective."""
    if not parcels_in_delivery_order:
        return 1.0, [], 0.0

    lat, lon = config.depot_lat, config.depot_lon
    clock_minutes = minutes(config.depot_departure_time)
    compliant = []
    total_wait_minutes = 0.0
    for parcel in parcels_in_delivery_order:
        dist_km = haversine_km(lat, lon, parcel.latitude, parcel.longitude)
        clock_minutes += (dist_km / max(vehicle.avg_speed_kmh, 1e-6)) * 60.0
        start = minutes(parcel.time_window_start)
        end = minutes(parcel.time_window_end)
        if clock_minutes < start:
            total_wait_minutes += start - clock_minutes
            clock_minutes = start
            compliant.append(True)
        elif clock_minutes <= end:
            compliant.append(True)
        else:
            compliant.append(False)
        service = config.service_time_minutes
        if parcel.two_person_lift:
            service *= config.two_person_lift_service_multiplier
        clock_minutes += service
        lat, lon = parcel.latitude, parcel.longitude

    return sum(compliant) / len(compliant), compliant, total_wait_minutes


def vehicle_metrics(parcel_objs: list, vehicle: VehicleTypeSpec, config: AssignmentConfig) -> dict:
    """Aggregate metrics for one candidate (parcel set, vehicle type) pairing
    — the building block for both the NSGA-II objectives and the persisted
    `VirtualVehicle`/`LoadPlan` summaries."""
    weight = sum(p.weight_kg for p in parcel_objs)
    volume = sum(p.volume_m3 for p in parcel_objs)
    points = [(p.latitude, p.longitude) for p in parcel_objs]
    order, distance = nearest_neighbor_tour(config.depot_lat, config.depot_lon, points)
    ordered_parcels = [parcel_objs[i] for i in order]

    compliance, flags, total_wait_minutes = schedule_time_window_compliance(ordered_parcels, vehicle, config)
    util_weight = weight / vehicle.capacity_kg if vehicle.capacity_kg else 0.0
    util_volume = volume / vehicle.capacity_m3 if vehicle.capacity_m3 else 0.0
    cost = vehicle.fixed_cost + vehicle.cost_per_km * distance

    return {
        "weight": weight,
        "volume": volume,
        "count": len(parcel_objs),
        "distance": distance,
        "compliance": compliance,
        "compliant_count": sum(flags),
        "cost": cost,
        "util_weight": util_weight,
        "util_volume": util_volume,
        # A van full of pillows is fully utilized — utilization is the
        # binding resource, not weight alone (spec 3.2).
        "utilization": max(util_weight, util_volume),
        "ordered_parcels": ordered_parcels,
        "total_wait_minutes": total_wait_minutes,
    }


N_OBJECTIVES = 4
N_CONSTRAINTS = 8


#: Bound on the per-problem-instance slot caches (F5): large enough to cover
#: a full run's worth of distinct slot contents without unbounded growth
#: across long runs.
SLOT_CACHE_MAXSIZE = 200_000


class AssignmentProblem(Problem):
    def __init__(self, parcels: list, catalog: tuple[VehicleTypeSpec, ...], config: AssignmentConfig, n_slots: int | None = None):
        if not parcels:
            raise ValueError("AssignmentProblem requires at least one parcel.")
        if not catalog:
            raise ValueError("AssignmentProblem requires a non-empty vehicle catalog snapshot.")

        self.parcels = parcels
        self.catalog = catalog
        self.config = config
        self.n = len(parcels)
        self.K = n_slots if n_slots is not None else slot_budget(parcels, catalog, config)
        self.T = len(catalog)

        # Per-instance caches (F5): slot contents repeat constantly across a
        # population and across generations, so memoise the expensive parts
        # of a slot's evaluation on (frozenset(parcel_indices), type_idx).
        # Kept on the instance (never module-level) so a cache never leaks
        # across separate runs and can't silently corrupt seeded
        # reproducibility. The tour only depends on the parcel set, not the
        # vehicle type, so it gets its own cache shared across all types.
        self._tour_cache: OrderedDict[frozenset, tuple[list[int], float]] = OrderedDict()
        self._slot_cache: OrderedDict[tuple[frozenset, int], dict] = OrderedDict()
        self._cache_hits = 0
        self._cache_misses = 0

        n_var = self.n + self.K
        xl = np.zeros(n_var)
        xu = np.concatenate([np.full(self.n, self.K - 1), np.full(self.K, self.T - 1)])
        super().__init__(n_var=n_var, n_obj=N_OBJECTIVES, n_ieq_constr=N_CONSTRAINTS, xl=xl, xu=xu, vtype=int)

    def _evaluate(self, X, out, *args, **kwargs):
        F = np.zeros((len(X), N_OBJECTIVES))
        G = np.zeros((len(X), N_CONSTRAINTS))
        for i, row in enumerate(X):
            F[i], G[i] = self.evaluate_individual(row)
        out["F"] = F
        out["G"] = G

    def cache_hit_rate(self) -> float:
        total = self._cache_hits + self._cache_misses
        return self._cache_hits / total if total else 0.0

    def _get_tour(self, parcel_indices: tuple[int, ...]) -> tuple[list[int], float]:
        key = frozenset(parcel_indices)
        cached = self._tour_cache.get(key)
        if cached is not None:
            self._tour_cache.move_to_end(key)
            return cached

        points = [(self.parcels[i].latitude, self.parcels[i].longitude) for i in parcel_indices]
        order, distance = nearest_neighbor_tour(self.config.depot_lat, self.config.depot_lon, points)
        result = ([parcel_indices[i] for i in order], distance)

        self._tour_cache[key] = result
        if len(self._tour_cache) > SLOT_CACHE_MAXSIZE:
            self._tour_cache.popitem(last=False)
        return result

    def _evaluate_slot(self, parcel_indices: tuple[int, ...], type_idx: int) -> dict:
        cache_key = (frozenset(parcel_indices), type_idx)
        cached = self._slot_cache.get(cache_key)
        if cached is not None:
            self._slot_cache.move_to_end(cache_key)
            self._cache_hits += 1
            return cached
        self._cache_misses += 1

        vehicle = self.catalog[type_idx]
        ordered_indices, distance = self._get_tour(parcel_indices)
        ordered_parcels = [self.parcels[i] for i in ordered_indices]

        weight = sum(self.parcels[i].weight_kg for i in parcel_indices)
        volume = sum(self.parcels[i].volume_m3 for i in parcel_indices)
        compliance, flags, total_wait_minutes = schedule_time_window_compliance(ordered_parcels, vehicle, self.config)
        util_weight = weight / vehicle.capacity_kg if vehicle.capacity_kg else 0.0
        util_volume = volume / vehicle.capacity_m3 if vehicle.capacity_m3 else 0.0
        cost = vehicle.fixed_cost + vehicle.cost_per_km * distance
        # F7: the GA only needs the feasibility verdict, never the LIFO
        # exception list -- computing it here would be pure waste, repeated
        # per slot/individual/generation.
        placement_ok = attempt_placement(ordered_parcels, vehicle, collect_exceptions=False) is not None

        result = {
            "weight": weight,
            "volume": volume,
            "count": len(parcel_indices),
            "distance": distance,
            "compliance": compliance,
            "compliant_count": sum(flags),
            "cost": cost,
            "util_weight": util_weight,
            "util_volume": util_volume,
            "utilization": max(util_weight, util_volume),
            "ordered_parcels": ordered_parcels,
            "total_wait_minutes": total_wait_minutes,
            "placement_ok": placement_ok,
        }
        self._slot_cache[cache_key] = result
        if len(self._slot_cache) > SLOT_CACHE_MAXSIZE:
            self._slot_cache.popitem(last=False)
        return result

    def evaluate_individual(self, row) -> tuple[np.ndarray, np.ndarray]:
        slots, type_of_slot = decode(row, self.n, self.K)

        used_metrics = []
        g_weight = g_volume = g_count = g_dim = g_hazmat = g_refrig = g_stack = 0.0

        for slot_idx, parcel_indices in slots.items():
            type_idx = int(np.clip(type_of_slot[slot_idx], 0, self.T - 1))
            vehicle = self.catalog[type_idx]

            m = self._evaluate_slot(tuple(parcel_indices), type_idx)
            used_metrics.append(m)

            g_weight += max(0.0, m["weight"] - vehicle.capacity_kg)
            g_volume += max(0.0, m["volume"] - vehicle.capacity_m3)
            g_count += max(0.0, m["count"] - vehicle.max_parcels)

            parcel_objs = [self.parcels[i] for i in parcel_indices]
            for p in parcel_objs:
                if not _dimension_fits(p, vehicle):
                    g_dim += 1.0
                if not _hazmat_ok(p, vehicle):
                    g_hazmat += 1.0
                if not _refrigeration_ok(p, vehicle):
                    g_refrig += 1.0

            if not m["placement_ok"]:
                g_stack += len(parcel_objs)

        # Utilization is intentionally averaged per *vehicle*, not weighted
        # by parcel count — it answers "how well-loaded is a typical
        # vehicle", not "how well-loaded is a typical parcel's vehicle".
        # Compliance below is weighted by parcel count instead, per the
        # spec's f3 definition (compliant parcels / total parcels); the two
        # objectives differ on purpose.
        mean_utilization = float(np.mean([m["utilization"] for m in used_metrics]))
        total_distance = float(sum(m["distance"] for m in used_metrics))
        total_parcels = sum(m["count"] for m in used_metrics)
        mean_compliance = (
            sum(m["compliant_count"] for m in used_metrics) / total_parcels if total_parcels else 1.0
        )
        total_cost = float(sum(m["cost"] for m in used_metrics))

        f = np.array([-mean_utilization, total_distance, -mean_compliance, total_cost])
        # Constraint 8 (empty-slot consistency) is auto-satisfied by the
        # encoding itself — a slot only exists in `slots` if it holds a
        # parcel, and its type gene is always in [0, T-1] by construction
        # of `xu`. Kept as an explicit always-zero column so
        # `n_ieq_constr` matches the spec's numbered constraint list.
        g = np.array([g_weight, g_volume, g_count, g_dim, g_hazmat, g_refrig, g_stack, 0.0])
        return f, g


class WarmStartSampling(Sampling):
    """Seeds a few individuals from the capacity-aware repaired clusters
    (Phase 2) instead of leaving the whole initial population random —
    gives NSGA-II a feasible starting region to search from (spec 3.3)."""

    def __init__(self, warm_start_rows: list[np.ndarray] | None = None, n_warm_start: int = 5):
        super().__init__()
        self.warm_start_rows = warm_start_rows or []
        self.n_warm_start = n_warm_start

    def _do(self, problem, n_samples, **kwargs):
        base = IntegerRandomSampling()._do(problem, n_samples, **kwargs)
        for i, row in enumerate(self.warm_start_rows[: min(self.n_warm_start, n_samples)]):
            base[i, : len(row)] = row
        return base


def warm_start_rows_from_clusters(
    parcels: list, clusters: dict[int, list], catalog: tuple[VehicleTypeSpec, ...], K: int
) -> list[np.ndarray]:
    """One individual: each capacity-aware-repaired cluster becomes its own
    vehicle slot (wrapping if there are more clusters than slots — should
    not happen since `slot_budget` sizes K to at least the cluster count),
    with the smallest catalog type that fits that cluster's aggregate
    load."""
    index_of_parcel = {p.parcel_id: i for i, p in enumerate(parcels)}
    n = len(parcels)
    row = np.zeros(n + K, dtype=int)

    for slot_idx, members in enumerate(clusters.values()):
        slot = slot_idx % K
        for p in members:
            idx = index_of_parcel.get(p.parcel_id)
            if idx is not None:
                row[idx] = slot

        weight = sum(p.weight_kg for p in members)
        volume = sum(p.volume_m3 for p in members)
        best_type_idx, best_capacity = 0, float("inf")
        for t_idx, vehicle in enumerate(catalog):
            if vehicle.capacity_kg >= weight and vehicle.capacity_m3 >= volume and vehicle.capacity_kg < best_capacity:
                best_type_idx, best_capacity = t_idx, vehicle.capacity_kg
        row[n + slot] = best_type_idx

    return [row]


class OverflowRepair(Repair):
    """Standard cheap repair for constrained assignment GAs (spec 3.3): if a
    slot overflows weight or volume capacity, move its lightest parcels to
    the least-loaded slot that has headroom for them. Does not touch
    dimensional/hazmat/refrigeration/stacking feasibility — those remain
    the constraint evaluator's job; this only relieves the two most common,
    cheaply-fixable overflow constraints so the GA spends less time on
    trivially-infeasible individuals."""

    def _do(self, problem: AssignmentProblem, X, **kwargs):
        for row in X:
            self._repair_row(problem, row)
        return X

    def _repair_row(self, problem: AssignmentProblem, row):
        # Decode once (F6): the old code re-decoded the whole row — an O(n)
        # walk — inside `_least_loaded_compatible_slot`, once per parcel
        # moved, per overflowing slot. Instead, decode once and maintain
        # running per-slot weight/volume totals, updated incrementally as
        # parcels move, so no further decode or `sum()` over slot members
        # is needed for the rest of this repair.
        slots, type_of_slot = decode(row, problem.n, problem.K)
        type_of_slot = np.clip(type_of_slot, 0, problem.T - 1).astype(int)

        slot_weight = np.zeros(problem.K)
        slot_volume = np.zeros(problem.K)
        for slot_idx, parcel_indices in slots.items():
            slot_weight[slot_idx] = sum(problem.parcels[i].weight_kg for i in parcel_indices)
            slot_volume[slot_idx] = sum(problem.parcels[i].volume_m3 for i in parcel_indices)

        for slot_idx, parcel_indices in list(slots.items()):
            vehicle = problem.catalog[type_of_slot[slot_idx]]
            if slot_weight[slot_idx] <= vehicle.capacity_kg and slot_volume[slot_idx] <= vehicle.capacity_m3:
                continue

            members = sorted(parcel_indices, key=lambda i: problem.parcels[i].weight_kg)
            for idx in members:
                if slot_weight[slot_idx] <= vehicle.capacity_kg and slot_volume[slot_idx] <= vehicle.capacity_m3:
                    break
                parcel = problem.parcels[idx]
                target = self._least_loaded_compatible_slot(
                    problem, type_of_slot, slot_weight, slot_volume, slot_idx, parcel
                )
                if target is None:
                    continue
                row[idx] = target
                slot_weight[slot_idx] -= parcel.weight_kg
                slot_volume[slot_idx] -= parcel.volume_m3
                slot_weight[target] += parcel.weight_kg
                slot_volume[target] += parcel.volume_m3

    def _least_loaded_compatible_slot(
        self, problem: AssignmentProblem, type_of_slot, slot_weight, slot_volume, exclude_slot: int, parcel
    ):
        best_slot, best_load = None, float("inf")
        for slot_idx in range(problem.K):
            if slot_idx == exclude_slot:
                continue
            vehicle = problem.catalog[type_of_slot[slot_idx]]
            weight = slot_weight[slot_idx] + parcel.weight_kg
            volume = slot_volume[slot_idx] + parcel.volume_m3
            if weight > vehicle.capacity_kg or volume > vehicle.capacity_m3:
                continue
            load_fraction = max(
                weight / vehicle.capacity_kg if vehicle.capacity_kg else 1.0,
                volume / vehicle.capacity_m3 if vehicle.capacity_m3 else 1.0,
            )
            if load_fraction < best_load:
                best_slot, best_load = slot_idx, load_fraction
        return best_slot


def run_nsga2(
    parcels: list,
    catalog: tuple[VehicleTypeSpec, ...],
    config: AssignmentConfig,
    *,
    seed: int,
    warm_start_clusters: dict[int, list] | None = None,
):
    """Runs NSGA-II and returns `(problem, res)` with `res.F`/`res.X`/`res.G`
    intact — never discarded, unlike the defect this replaces. `seed` is
    always threaded from the caller; nothing in this module hardcodes one."""
    if not parcels:
        raise ValueError("No parcels to assign.")
    if not catalog:
        raise ValueError("Empty vehicle catalog snapshot.")

    n_warm_clusters = len(warm_start_clusters) if warm_start_clusters else 0
    K = slot_budget(parcels, catalog, config, n_warm_clusters)
    problem = AssignmentProblem(parcels, catalog, config, n_slots=K)

    warm_rows = warm_start_rows_from_clusters(parcels, warm_start_clusters, catalog, K) if warm_start_clusters else []

    algorithm = NSGA2(
        pop_size=config.population,
        sampling=WarmStartSampling(warm_rows, n_warm_start=config.warm_start_count),
        crossover=SBX(prob=0.9, eta=15, vtype=float, repair=RoundingRepair()),
        mutation=PM(prob=1.0 / problem.n_var, eta=20, vtype=float, repair=RoundingRepair()),
        repair=OverflowRepair(),
        eliminate_duplicates=True,
    )

    res = minimize(
        problem,
        algorithm,
        termination=("n_gen", config.generations),
        seed=seed,
        verbose=False,
    )
    logger.debug(
        "run_nsga2: slot-cache hit rate %.1f%% (%d hits / %d misses)",
        problem.cache_hit_rate() * 100.0, problem._cache_hits, problem._cache_misses,
    )
    return problem, res
