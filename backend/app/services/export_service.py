import csv
import io
from fastapi import HTTPException
from app.models.load_plan import LoadPlan
from app.models.parcel import Parcel

CSV_FIELDS = ["plan_id", "virtual_vehicle_id", "vehicle_type", "parcel_id", "delivery_sequence", "load_sequence", "stack_layer", "load_position_x", "load_position_y", "load_position_z", "length_cm", "width_cm", "height_cm", "weight_kg", "volume_m3", "fragile", "stackable", "time_window_start", "time_window_end"]

async def _rows(plan_id):
    plan = await LoadPlan.find_one(LoadPlan.plan_id == plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Load plan not found")
    ids = [a.parcel_id for v in plan.vehicles for a in v.assignments]
    parcels = await Parcel.find({"parcel_id": {"$in": ids}}).to_list()
    return plan, {p.parcel_id: p for p in parcels}

def _parcel_payload(assignment, parcel):
    return {"parcel_id": parcel.parcel_id, "delivery_sequence": assignment.delivery_sequence,
            "load_sequence": assignment.load_sequence, "stack_layer": assignment.stack_layer,
            "load_position_x": assignment.load_position_x, "load_position_y": assignment.load_position_y,
            "load_position_z": assignment.load_position_z,
            "length_cm": assignment.placed_length_cm or parcel.length_cm,
            "width_cm": assignment.placed_width_cm or parcel.width_cm,
            "height_cm": assignment.placed_height_cm or parcel.height_cm,
            "weight_kg": parcel.weight_kg, "volume_m3": parcel.volume_m3,
            "fragile": parcel.fragile, "stackable": parcel.stackable,
            "time_window_start": parcel.time_window_start, "time_window_end": parcel.time_window_end}

async def load_plan_payload(plan_id):
    plan, parcels = await _rows(plan_id)
    return {"plan_id": plan.plan_id, "depot_id": plan.depot_id, "delivery_date": plan.delivery_date.isoformat(),
            "status": plan.status, "n_parcels": plan.n_parcels, "n_vehicles": plan.n_vehicles,
            "mean_utilization": plan.mean_utilization, "total_distance_km": plan.total_distance_km,
            "mean_time_window_compliance": plan.mean_time_window_compliance,
            "total_fleet_cost": plan.total_fleet_cost,
            "vehicles": [{"virtual_vehicle_id": v.virtual_vehicle_id, "vehicle_type": v.vehicle_type_code,
                "status": v.status, "ready_at": v.ready_at.isoformat() if v.ready_at else None,
                "capacity_kg": v.capacity_kg, "capacity_m3": v.capacity_m3,
                "used_weight_kg": v.used_weight_kg, "used_volume_m3": v.used_volume_m3,
                "utilization": v.utilization,
                "parcel_count": v.parcel_count, "cargo_length_cm": v.cargo_length_cm,
                "cargo_width_cm": v.cargo_width_cm, "cargo_height_cm": v.cargo_height_cm,
                "estimated_distance_km": v.estimated_distance_km,
                "time_window_compliance": v.time_window_compliance, "fleet_cost": v.fleet_cost,
                "parcels": [_parcel_payload(a, parcels[a.parcel_id]) for a in v.assignments]}
                for v in plan.vehicles]}

async def load_plan_csv(plan_id):
    plan, parcels = await _rows(plan_id)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for v in plan.vehicles:
        for a in v.assignments:
            writer.writerow({"plan_id": plan_id, "virtual_vehicle_id": v.virtual_vehicle_id,
                             "vehicle_type": v.vehicle_type_code, **_parcel_payload(a, parcels[a.parcel_id])})
    return output.getvalue()
