"""Read-only JSON and CSV projections of persisted load plans."""
from __future__ import annotations

import csv
import io

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.load_plan import LoadPlan
from app.models.parcel import Parcel
from app.models.parcel_assignment import ParcelAssignment
from app.models.virtual_vehicle import VirtualVehicle


CSV_FIELDS = [
    "plan_id", "virtual_vehicle_id", "vehicle_type", "parcel_id",
    "delivery_sequence", "load_sequence", "stack_layer",
    "load_position_x", "load_position_y", "load_position_z",
    "length_cm", "width_cm", "height_cm", "weight_kg", "volume_m3",
    "fragile", "stackable", "time_window_start", "time_window_end",
]


def _rows(db: Session, plan_id: str):
    plan = db.query(LoadPlan).filter(LoadPlan.plan_id == plan_id).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="Load plan not found")
    vehicles = (
        db.query(VirtualVehicle)
        .filter(VirtualVehicle.plan_id == plan_id)
        .order_by(VirtualVehicle.virtual_vehicle_id)
        .all()
    )
    assignments = (
        db.query(ParcelAssignment, Parcel)
        .join(Parcel, Parcel.parcel_id == ParcelAssignment.parcel_id)
        .filter(ParcelAssignment.plan_id == plan_id)
        .order_by(ParcelAssignment.virtual_vehicle_id, ParcelAssignment.delivery_sequence)
        .all()
    )
    return plan, vehicles, assignments


def load_plan_payload(db: Session, plan_id: str) -> dict:
    plan, vehicles, assignment_rows = _rows(db, plan_id)
    parcels_by_vehicle: dict[str, list[dict]] = {v.virtual_vehicle_id: [] for v in vehicles}
    for assignment, parcel in assignment_rows:
        parcels_by_vehicle.setdefault(assignment.virtual_vehicle_id, []).append({
            "parcel_id": parcel.parcel_id,
            "delivery_sequence": assignment.delivery_sequence,
            "load_sequence": assignment.load_sequence,
            "stack_layer": assignment.stack_layer,
            "load_position_x": assignment.load_position_x,
            "load_position_y": assignment.load_position_y,
            "load_position_z": assignment.load_position_z,
            "length_cm": assignment.placed_length_cm or parcel.length_cm,
            "width_cm": assignment.placed_width_cm or parcel.width_cm,
            "height_cm": assignment.placed_height_cm or parcel.height_cm,
            "weight_kg": parcel.weight_kg,
            "volume_m3": parcel.volume_m3,
            "fragile": parcel.fragile,
            "stackable": parcel.stackable,
            "time_window_start": parcel.time_window_start,
            "time_window_end": parcel.time_window_end,
        })

    return {
        "plan_id": plan.plan_id,
        "depot_id": plan.depot_id,
        "delivery_date": plan.delivery_date.isoformat(),
        "status": plan.status,
        "n_parcels": plan.n_parcels,
        "n_vehicles": plan.n_vehicles,
        "mean_utilization": plan.mean_utilization,
        "total_distance_km": plan.total_distance_km,
        "mean_time_window_compliance": plan.mean_time_window_compliance,
        "total_fleet_cost": plan.total_fleet_cost,
        "vehicles": [{
            "virtual_vehicle_id": v.virtual_vehicle_id,
            "vehicle_type": v.vehicle_type,
            "capacity_kg": v.capacity_kg,
            "capacity_m3": v.capacity_m3,
            "used_weight_kg": v.used_weight_kg,
            "used_volume_m3": v.used_volume_m3,
            "parcel_count": v.parcel_count,
            "cargo_length_cm": v.cargo_length_cm,
            "cargo_width_cm": v.cargo_width_cm,
            "cargo_height_cm": v.cargo_height_cm,
            "estimated_distance_km": v.estimated_distance_km,
            "time_window_compliance": v.time_window_compliance,
            "fleet_cost": v.fleet_cost,
            "parcels": parcels_by_vehicle.get(v.virtual_vehicle_id, []),
        } for v in vehicles],
    }


def load_plan_csv(db: Session, plan_id: str) -> str:
    _plan, vehicles, assignment_rows = _rows(db, plan_id)
    vehicle_types = {v.virtual_vehicle_id: v.vehicle_type for v in vehicles}
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for assignment, parcel in assignment_rows:
        writer.writerow({
            "plan_id": plan_id,
            "virtual_vehicle_id": assignment.virtual_vehicle_id,
            "vehicle_type": vehicle_types[assignment.virtual_vehicle_id],
            "parcel_id": parcel.parcel_id,
            "delivery_sequence": assignment.delivery_sequence,
            "load_sequence": assignment.load_sequence,
            "stack_layer": assignment.stack_layer,
            "load_position_x": assignment.load_position_x,
            "load_position_y": assignment.load_position_y,
            "load_position_z": assignment.load_position_z,
            "length_cm": assignment.placed_length_cm or parcel.length_cm,
            "width_cm": assignment.placed_width_cm or parcel.width_cm,
            "height_cm": assignment.placed_height_cm or parcel.height_cm,
            "weight_kg": parcel.weight_kg,
            "volume_m3": parcel.volume_m3,
            "fragile": parcel.fragile,
            "stackable": parcel.stackable,
            "time_window_start": parcel.time_window_start,
            "time_window_end": parcel.time_window_end,
        })
    return output.getvalue()
