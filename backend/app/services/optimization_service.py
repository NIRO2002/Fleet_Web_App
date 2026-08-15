import uuid
import numpy as np
from sqlalchemy.orm import Session
from pymoo.core.problem import Problem
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize

from app.core.config import settings
from app.models.virtual_vehicle import VirtualVehicle
from app.routing.distance_matrix import nearest_neighbor_distance_km
from app.utils_time import time_window_compliance

VEHICLES = {
    "BIKE": {"capacity_kg": 25.0, "capacity_m3": 0.08},
    "THREE_WHEEL": {"capacity_kg": 150.0, "capacity_m3": 0.8},
    "VAN": {"capacity_kg": 1000.0, "capacity_m3": 8.0},
    "LORRY": {"capacity_kg": 5000.0, "capacity_m3": 25.0},
}

def metrics(parcels, vehicle_type, depot_lat, depot_lon):
    cap = VEHICLES[vehicle_type]
    weight = sum(p.weight_kg for p in parcels)
    volume = sum(p.volume_m3 for p in parcels)
    feasible = weight <= cap["capacity_kg"] and volume <= cap["capacity_m3"]

    distance = nearest_neighbor_distance_km(
        depot_lat, depot_lon, [(p.latitude, p.longitude) for p in parcels]
    )
    compliance = time_window_compliance(parcels)

    return {
        "feasible": feasible,
        "weight": weight,
        "volume": volume,
        "distance": distance,
        "compliance": compliance,
        "utilization_weight": weight / cap["capacity_kg"],
        "utilization_volume": volume / cap["capacity_m3"],
    }

class VehicleTypeNSGAProblem(Problem):
    def __init__(self, parcels, depot_lat, depot_lon):
        self.parcels = parcels
        self.names = list(VEHICLES)
        self.depot_lat = depot_lat
        self.depot_lon = depot_lon
        super().__init__(
            n_var=1, n_obj=3, n_ieq_constr=1,
            xl=np.array([0]), xu=np.array([len(self.names) - 1]), vtype=int
        )

    def _evaluate(self, X, out, *args, **kwargs):
        F, G = [], []
        for row in X:
            idx = max(0, min(len(self.names) - 1, int(round(row[0]))))
            name = self.names[idx]
            m = metrics(self.parcels, name, self.depot_lat, self.depot_lon)
            F.append([-m["utilization_weight"], m["distance"], -m["compliance"]])
            G.append([0.0 if m["feasible"] else 1.0])
        out["F"] = np.asarray(F)
        out["G"] = np.asarray(G)

def optimize_load(db: Session, parcels, depot_lat, depot_lon):
    if not parcels:
        raise ValueError("No parcels selected.")

    problem = VehicleTypeNSGAProblem(parcels, depot_lat, depot_lon)
    minimize(
        problem,
        NSGA2(pop_size=settings.nsga2_population),
        termination=("n_gen", settings.nsga2_generations),
        seed=42,
        verbose=False,
    )

    options = []
    for name, cap in VEHICLES.items():
        m = metrics(parcels, name, depot_lat, depot_lon)
        if not m["feasible"]:
            continue
        score = (
            0.45 * m["utilization_weight"]
            + 0.20 * m["utilization_volume"]
            + 0.20 * m["compliance"]
            + 0.15 / (1 + m["distance"])
        )
        options.append({
            "vehicle_type": name,
            "capacity_kg": cap["capacity_kg"],
            "capacity_m3": cap["capacity_m3"],
            "load_weight_kg": m["weight"],
            "load_volume_m3": m["volume"],
            "utilization_weight": m["utilization_weight"],
            "utilization_volume": m["utilization_volume"],
            "estimated_distance_km": m["distance"],
            "time_window_compliance": m["compliance"],
            "score": score,
        })

    if not options:
        raise ValueError("No vehicle type is feasible for this parcel set.")

    options.sort(key=lambda x: x["score"], reverse=True)
    selected = options[0]
    cluster_ids = {p.cluster_id for p in parcels if p.cluster_id is not None}
    cluster_id = next(iter(cluster_ids)) if len(cluster_ids) == 1 else None

    virtual_vehicle = VirtualVehicle(
        virtual_vehicle_id=f"VV-{uuid.uuid4().hex[:10].upper()}",
        vehicle_type=selected["vehicle_type"],
        capacity_kg=selected["capacity_kg"],
        capacity_m3=selected["capacity_m3"],
        used_weight_kg=selected["load_weight_kg"],
        used_volume_m3=selected["load_volume_m3"],
        cluster_id=cluster_id,
        destination_latitude=float(np.mean([p.latitude for p in parcels])),
        destination_longitude=float(np.mean([p.longitude for p in parcels])),
    )
    db.add(virtual_vehicle)
    db.commit()
    db.refresh(virtual_vehicle)

    return {
        "optimization_id": f"OPT-{uuid.uuid4().hex[:10].upper()}",
        "selected_vehicle": selected,
        "parcel_ids": [p.parcel_id for p in parcels],
        "cluster_id": cluster_id,
        "pareto_solutions": options,
        "virtual_vehicle_id": virtual_vehicle.virtual_vehicle_id,
    }, virtual_vehicle

def try_insert(db: Session, virtual_vehicle: VirtualVehicle, parcel):
    if virtual_vehicle.used_weight_kg + parcel.weight_kg > virtual_vehicle.capacity_kg:
        return False, "Insufficient weight capacity"
    if virtual_vehicle.used_volume_m3 + parcel.volume_m3 > virtual_vehicle.capacity_m3:
        return False, "Insufficient volume capacity"

    virtual_vehicle.used_weight_kg += parcel.weight_kg
    virtual_vehicle.used_volume_m3 += parcel.volume_m3
    virtual_vehicle.updated_at = __import__("datetime").datetime.utcnow()
    db.commit()
    return True, "Parcel inserted into existing virtual vehicle"
