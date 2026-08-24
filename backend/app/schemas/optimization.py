from datetime import date as date_type
from typing import Optional
from pydantic import BaseModel, model_validator

class OptimizationRequest(BaseModel):
    cluster_id: Optional[int] = None
    parcel_ids: Optional[list[str]] = None
    # Required whenever cluster_id is used: HDBSCAN labels restart at 0 per
    # (depot_id, delivery_date) planning instance (see
    # app/services/clustering_service.py), so a bare cluster_id is
    # ambiguous across instances without this scope. See
    # app/api/v1/optimization.py's cluster_id branch.
    depot_id: Optional[str] = None
    delivery_date: Optional[date_type] = None
    depot_latitude: Optional[float] = None
    depot_longitude: Optional[float] = None

    @model_validator(mode="after")
    def require_scope_for_cluster_id(self):
        if self.cluster_id is not None and (self.depot_id is None or self.delivery_date is None):
            raise ValueError("depot_id and delivery_date are required when cluster_id is used")
        return self

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
