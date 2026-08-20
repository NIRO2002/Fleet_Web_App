from datetime import date, datetime
from beanie import Document, Indexed
from pydantic import Field
from pymongo import ASCENDING, IndexModel
from app.utils_datetime import utcnow

PRIORITY_LEVELS = {"standard", "next_day", "express", "same_day"}

class Parcel(Document):
    parcel_id: Indexed(str, unique=True)
    depot_id: str | None = None
    delivery_date: date | None = None
    latitude: float
    longitude: float
    weight_kg: float
    volume_m3: float
    time_window_start: str
    time_window_end: str
    fragile: bool = False
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    dimensions_imputed: bool = False
    stackable: bool = True
    max_stack_weight_kg: float = 0.0
    loading_orientation_fixed: bool = False
    hazardous: bool = False
    hazmat_class: str | None = None
    requires_refrigeration: bool = False
    temp_min_celsius: float | None = None
    temp_max_celsius: float | None = None
    two_person_lift: bool = False
    do_not_tilt: bool = False
    priority_level: str = "standard"
    service_type: str = "door_to_door"
    is_noise: bool = False
    cluster_id: int | None = None
    cluster_probability: float | None = None
    status: str = "PENDING"
    plan_id: str | None = None
    carried_over_from_date: date | None = None
    created_at: datetime = Field(default_factory=utcnow)

    @property
    def special_handling(self) -> bool:
        return self.hazardous or self.requires_refrigeration or self.two_person_lift

    class Settings:
        name = "parcels"
        indexes = [IndexModel([("depot_id", ASCENDING), ("delivery_date", ASCENDING)]), "status"]
