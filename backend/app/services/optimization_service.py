"""NSGA-II load assignment orchestration (Phase 3 — the core fix).

Satisfies SO3/SO4/FR04: replaces the old fixed n_var=1
"pick-one-vehicle-type-for-a-fixed-parcel-list" scalarised heuristic (whose
`minimize()` result was discarded entirely — see docs/DESIGN_DECISIONS.md)
with `app.optimization.assignment_problem`'s genuine multi-objective
parcel-to-vehicle-slot assignment. Vehicle data is loaded once per run from
`vehicle_type_catalog` via `vehicle_catalog_service` — never a literal
here. The *whole* Pareto front is always returned; the single solution that
gets persisted as `VirtualVehicle`/`ParcelAssignment` rows is chosen by
knee-point selection (or a caller preference) among already non-dominated
solutions only, never as the optimizer's own objective.

Full pipeline orchestration (clustering -> capacity-aware repair -> this
module -> CSV/JSON export) is Phase 4's `pipeline.py`. This module expects
an already-assembled parcel list (e.g. one clustering instance) and turns
it into a persisted `LoadPlan`.
"""
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.load_plan import LoadPlan
from app.models.parcel_assignment import ParcelAssignment
from app.models.virtual_vehicle import VirtualVehicle
from app.optimization.assignment_problem import (
    AssignmentConfig,
    decode,
    load_catalog_snapshot,
    run_nsga2,
    vehicle_metrics,
)
from app.optimization.placement import attempt_placement
from app.optimization.selection import hypervolume, select_solution
from app.services.vehicle_catalog_service import VehicleCatalogCache


def _single_cluster_id(parcel_objs) -> int | None:
    ids = {p.cluster_id for p in parcel_objs if p.cluster_id is not None}
    return next(iter(ids)) if len(ids) == 1 else None


def optimize_load(
    db: Session,
    parcels: list,
    *,
    depot_id: str,
    depot_lat: float,
    depot_lon: float,
    delivery_date=None,
    clustering_method: str = "hdbscan",
    seed: int = 0,
    config: AssignmentConfig | None = None,
    warm_start_clusters: dict[int, list] | None = None,
    catalog_cache: VehicleCatalogCache | None = None,
    preference_weights: list[float] | None = None,
):
    """Runs NSGA-II over `parcels` and persists the selected solution as a
    `LoadPlan` with one `VirtualVehicle` + a set of `ParcelAssignment` rows
    per used vehicle slot. Returns `(result_dict, load_plan)`.

    `depot_id` is required (not inferred) — the vehicle catalog and the
    plan's (depot_id, delivery_date) key both depend on it.
    """
    if not parcels:
        raise ValueError("No parcels selected.")

    started = time.perf_counter()
    config = config or AssignmentConfig(depot_lat=depot_lat, depot_lon=depot_lon)
    catalog = load_catalog_snapshot(db, depot_id, delivery_date, cache=catalog_cache)

    problem, res = run_nsga2(parcels, catalog, config, seed=seed, warm_start_clusters=warm_start_clusters)
    idx, F, X, G = select_solution(res, preference_weights)
    front_hypervolume = hypervolume(F)

    selected_row = X[idx]
    slots, type_of_slot = decode(selected_row, problem.n, problem.K)
    used_slots = {sidx: members for sidx, members in slots.items() if members}

    plan_id = f"PLAN-{uuid.uuid4().hex[:10].upper()}"
    vehicles_summary = []
    virtual_vehicles = []
    pending_assignments = []
    utilizations, distances, compliances, costs = [], [], [], []

    for slot_idx, parcel_indices in used_slots.items():
        type_idx = int(max(0, min(problem.T - 1, type_of_slot[slot_idx])))
        vehicle_spec = catalog[type_idx]
        parcel_objs = [parcels[i] for i in parcel_indices]

        m = vehicle_metrics(parcel_objs, vehicle_spec, config)
        placement = attempt_placement(m["ordered_parcels"], vehicle_spec)

        utilizations.append(m["utilization"])
        distances.append(m["distance"])
        compliances.append(m["compliance"])
        costs.append(m["cost"])

        vv = VirtualVehicle(
            virtual_vehicle_id=f"VV-{uuid.uuid4().hex[:10].upper()}",
            depot_id=depot_id,
            delivery_date=delivery_date,
            plan_id=plan_id,
            vehicle_type=vehicle_spec.code,
            capacity_kg=vehicle_spec.capacity_kg,
            capacity_m3=vehicle_spec.capacity_m3,
            used_weight_kg=m["weight"],
            used_volume_m3=m["volume"],
            parcel_count=m["count"],
            max_parcels=vehicle_spec.max_parcels,
            estimated_distance_km=m["distance"],
            time_window_compliance=m["compliance"],
            fleet_cost=m["cost"],
            is_refrigerated=vehicle_spec.is_refrigerated,
            is_hazmat_certified=vehicle_spec.is_hazmat_certified,
            cargo_length_cm=vehicle_spec.cargo_length_cm,
            cargo_width_cm=vehicle_spec.cargo_width_cm,
            cargo_height_cm=vehicle_spec.cargo_height_cm,
            cluster_id=_single_cluster_id(parcel_objs),
            destination_latitude=float(sum(p.latitude for p in parcel_objs) / len(parcel_objs)),
            destination_longitude=float(sum(p.longitude for p in parcel_objs) / len(parcel_objs)),
        )
        db.add(vv)
        virtual_vehicles.append(vv)

        for position, parcel in enumerate(m["ordered_parcels"], start=1):
            placed = placement.placements.get(parcel.parcel_id) if placement else None
            pending_assignments.append(
                ParcelAssignment(
                    plan_id=plan_id,
                    virtual_vehicle_id=vv.virtual_vehicle_id,
                    parcel_id=parcel.parcel_id,
                    delivery_sequence=position,
                    load_sequence=placed.load_sequence if placed else position,
                    stack_layer=placed.layer if placed else 0,
                    load_position_x=placed.x if placed else 0.0,
                    load_position_y=placed.y if placed else 0.0,
                    load_position_z=placed.z if placed else 0.0,
                )
            )

        vehicles_summary.append(
            {
                "virtual_vehicle_id": vv.virtual_vehicle_id,
                "vehicle_type": vehicle_spec.code,
                "capacity_kg": vehicle_spec.capacity_kg,
                "capacity_m3": vehicle_spec.capacity_m3,
                "load_weight_kg": m["weight"],
                "load_volume_m3": m["volume"],
                "utilization_weight": m["util_weight"],
                "utilization_volume": m["util_volume"],
                "estimated_distance_km": m["distance"],
                "time_window_compliance": m["compliance"],
                "fleet_cost": m["cost"],
                "delivery_sequence_is_estimate": True,
                "load_order_exceptions": placement.load_order_exceptions if placement else [],
            }
        )

    for assignment in pending_assignments:
        db.add(assignment)

    plan = LoadPlan(
        plan_id=plan_id,
        depot_id=depot_id,
        delivery_date=delivery_date,
        clustering_method=clustering_method,
        seed=seed,
        catalog_snapshot=[asdict(v) for v in catalog],
        n_parcels=len(parcels),
        n_vehicles=len(vehicles_summary),
        mean_utilization=sum(utilizations) / len(utilizations) if utilizations else 0.0,
        total_distance_km=sum(distances),
        mean_time_window_compliance=sum(compliances) / len(compliances) if compliances else 0.0,
        total_fleet_cost=sum(costs),
        hypervolume=front_hypervolume,
        runtime_seconds=time.perf_counter() - started,
    )
    db.add(plan)
    db.commit()
    for vv in virtual_vehicles:
        db.refresh(vv)

    result = {
        "plan_id": plan_id,
        "optimization_id": plan_id,  # kept for the old response shape; Phase 4 retires it
        "seed": seed,
        "clustering_method": clustering_method,
        "cluster_id": _single_cluster_id(parcels),
        "parcel_ids": [p.parcel_id for p in parcels],
        "virtual_vehicle_id": vehicles_summary[0]["virtual_vehicle_id"] if len(vehicles_summary) == 1 else None,
        "virtual_vehicle_ids": [v["virtual_vehicle_id"] for v in vehicles_summary],
        "selected_vehicle": vehicles_summary[0] if vehicles_summary else None,
        "vehicles": vehicles_summary,
        "pareto_solutions": [
            {
                "utilization": -row[0],
                "estimated_distance_km": row[1],
                "time_window_compliance": -row[2],
                "fleet_cost": row[3],
            }
            for row in F.tolist()
        ],
        "hypervolume": front_hypervolume,
    }
    return result, virtual_vehicles


def try_insert(db: Session, virtual_vehicle: VirtualVehicle, parcel):
    """Weight/volume-only fit check. Deliberately left as-is (Phase 5 —
    `insertion_service.py` — replaces this wholesale with the full
    constraint set: dimensions, hazmat/refrigeration, actual re-run
    placement, schedule feasibility, detour bound); only the deprecated
    `datetime.utcnow()` call is fixed here since the file is already being
    touched for Phase 3."""
    if virtual_vehicle.used_weight_kg + parcel.weight_kg > virtual_vehicle.capacity_kg:
        return False, "Insufficient weight capacity"
    if virtual_vehicle.used_volume_m3 + parcel.volume_m3 > virtual_vehicle.capacity_m3:
        return False, "Insufficient volume capacity"

    virtual_vehicle.used_weight_kg += parcel.weight_kg
    virtual_vehicle.used_volume_m3 += parcel.volume_m3
    virtual_vehicle.updated_at = datetime.now(timezone.utc)
    db.commit()
    return True, "Parcel inserted into existing virtual vehicle"
