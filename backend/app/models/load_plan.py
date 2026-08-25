from datetime import date, datetime
from beanie import Document, Indexed
from pydantic import Field
from app.models.virtual_vehicle import VirtualVehicle
from app.utils_datetime import utcnow
from app.db.bson import DATE_BSON_ENCODERS

class LoadPlan(Document):
    plan_id: Indexed(str, unique=True)
    depot_id: str
    delivery_date: date
    status: str = "DRAFT"
    clustering_method: str
    seed: int
    catalog_snapshot: list[dict] = Field(default_factory=list)
    n_parcels: int
    n_vehicles: int
    n_parcels_with_imputed_dimensions: int = 0
    n_carryover_parcels: int = 0
    repair_cluster_status: dict[str, dict] = Field(default_factory=dict)
    excluded_infeasible_cluster_count: int = 0
    run_manifest: dict | None = None
    mean_utilization: float
    total_distance_km: float
    mean_time_window_compliance: float
    total_fleet_cost: float
    hypervolume: float | None = None
    runtime_seconds: float
    vehicles: list[VirtualVehicle] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    class Settings:
        name = "load_plans"
        bson_encoders = DATE_BSON_ENCODERS
