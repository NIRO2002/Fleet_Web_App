from datetime import datetime
from beanie import Document, Indexed
from pydantic import Field
from app.utils_datetime import utcnow

class VehicleTypeCatalog(Document):
    code: Indexed(str, unique=True)
    display_name: str
    capacity_kg: float
    capacity_m3: float
    cargo_length_cm: float
    cargo_width_cm: float
    cargo_height_cm: float
    max_parcels: int
    max_stack_layers: int = 1
    fixed_cost: float = 0.0
    cost_per_km: float = 0.0
    avg_speed_kmh: float = 30.0
    is_refrigerated: bool = False
    temp_min_celsius: float | None = None
    temp_max_celsius: float | None = None
    is_hazmat_certified: bool = False
    has_tail_lift: bool = False
    min_road_width_m: float | None = None
    model_name: str | None = None
    gross_vehicle_weight_kg: float | None = None
    cost_per_trip_reference: float | None = None
    vehicle_max_stack_weight_kg: float = 1_000_000.0
    max_speed_kmh: float | None = None
    available_from: str = "00:00"
    available_until: str = "23:59"
    source_reference: str | None = None
    depot_id: str | None = None
    is_active: bool = True
    source: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    class Settings:
        name = "vehicle_type_catalog"
