from datetime import date, datetime
from beanie import Document, Indexed
from pydantic import Field, field_validator
from pymongo import ASCENDING, IndexModel
from app.utils_datetime import utcnow
from app.db.bson import DATE_BSON_ENCODERS

PRIORITY_LEVELS = {"standard", "next_day", "express", "same_day", "priority"}
SERVICE_TYPES = {"door_to_door", "collection_point", "locker_drop", "standard"}

class Parcel(Document):
    parcel_id: Indexed(str, unique=True)
    dataset_id: str | None = None
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
    cluster_assignment_status: str | None = None
    noise_resolution: str | None = None
    unassigned_reason: str | None = None
    status: str = "PENDING"
    plan_id: str | None = None
    carried_over_from_date: date | None = None
    created_at: datetime = Field(default_factory=utcnow)

    @property
    def special_handling(self) -> bool:
        return self.hazardous or self.requires_refrigeration or self.two_person_lift

    @field_validator("priority_level")
    @classmethod
    def validate_priority_level(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in PRIORITY_LEVELS:
            raise ValueError(f"priority_level must be one of {sorted(PRIORITY_LEVELS)}")
        return normalized

    @field_validator("service_type")
    @classmethod
    def validate_service_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SERVICE_TYPES:
            raise ValueError(f"service_type must be one of {sorted(SERVICE_TYPES)}")
        return normalized

    class Settings:
        name = "parcels"
        bson_encoders = DATE_BSON_ENCODERS
        # Supersedes the old (depot_id, delivery_date)-only index: MongoDB
        # compound indexes serve any query on a leading prefix of their
        # fields, so this one covers both the plain planning-instance scope
        # and the cluster_id-scoped lookup in api/v1/optimization.py without
        # needing two separate indexes.
        indexes = [
            IndexModel([("depot_id", ASCENDING), ("delivery_date", ASCENDING), ("cluster_id", ASCENDING)]),
            "dataset_id", "status",
        ]
