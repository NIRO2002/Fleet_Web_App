from datetime import datetime
from pydantic import BaseModel, Field
from app.models.parcel_assignment import ParcelAssignment
from app.utils_datetime import utcnow

class VirtualVehicle(BaseModel):
    virtual_vehicle_id: str
    vehicle_type_code: str
    status: str = "LOADING"
    capacity_kg: float
    capacity_m3: float
    used_weight_kg: float = 0.0
    used_volume_m3: float = 0.0
    parcel_count: int = 0
    max_parcels: int | None = None
    utilization: float = 0.0
    estimated_distance_km: float = 0.0
    time_window_compliance: float | None = None
    fleet_cost: float = 0.0
    is_refrigerated: bool = False
    is_hazmat_certified: bool = False
    cargo_length_cm: float
    cargo_width_cm: float
    cargo_height_cm: float
    cluster_id: int | None = None
    destination_latitude: float | None = None
    destination_longitude: float | None = None
    assignments: list[ParcelAssignment] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utcnow)
    @property
    def vehicle_type(self) -> str:
        return self.vehicle_type_code
