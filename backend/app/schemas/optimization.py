from typing import Optional
from pydantic import BaseModel

class OptimizationRequest(BaseModel):
    cluster_id: Optional[int] = None
    parcel_ids: Optional[list[str]] = None
    depot_latitude: Optional[float] = None
    depot_longitude: Optional[float] = None

class VehicleOption(BaseModel):
    vehicle_type: str
    capacity_kg: float
    capacity_m3: float
    load_weight_kg: float
    load_volume_m3: float
    utilization_weight: float
    utilization_volume: float
    estimated_distance_km: float
    time_window_compliance: float
    score: float

class OptimizationResponse(BaseModel):
    optimization_id: str
    selected_vehicle: VehicleOption
    parcel_ids: list[str]
    cluster_id: Optional[int] = None
    pareto_solutions: list[VehicleOption]

class InsertionResponse(BaseModel):
    virtual_vehicle_id: str
    inserted: bool
    reason: str
    remaining_weight_kg: float
    remaining_volume_m3: float
