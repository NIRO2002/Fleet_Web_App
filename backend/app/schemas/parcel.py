from datetime import date as date_type
from typing import Optional
from pydantic import BaseModel, Field, field_validator

#: "priority" added for Fix Pass 4 S5 -- present in the real dataset
#: (~10% of parcels_sample_36000.csv) as a distinct tier from "express", not
#: a typo or alias for it.
PRIORITY_LEVELS = {"standard", "next_day", "express", "same_day", "priority"}
PARCEL_STATUSES = {"PENDING", "PLANNED", "DELIVERED", "FAILED"}


class ParcelIn(BaseModel):
    parcel_id: str = Field(min_length=1, max_length=64)
    dataset_id: Optional[str] = Field(default=None, max_length=64)
    depot_id: Optional[str] = Field(default=None, max_length=32)
    delivery_date: Optional[date_type] = None

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    weight_kg: float = Field(gt=0)
    volume_m3: float = Field(gt=0)
    time_window_start: str
    time_window_end: str
    fragile: bool = False

    length_cm: Optional[float] = Field(default=None, gt=0)
    width_cm: Optional[float] = Field(default=None, gt=0)
    height_cm: Optional[float] = Field(default=None, gt=0)
    # Set by the importer (F12) when length/width/height were absent and a
    # cube was imputed from volume_m3 -- never expected as caller input.
    dimensions_imputed: bool = False

    stackable: bool = True
    max_stack_weight_kg: float = Field(default=0.0, ge=0)
    loading_orientation_fixed: bool = False

    hazardous: bool = False
    hazmat_class: Optional[str] = Field(default=None, max_length=16)
    requires_refrigeration: bool = False
    temp_min_celsius: Optional[float] = None
    temp_max_celsius: Optional[float] = None

    two_person_lift: bool = False
    do_not_tilt: bool = False

    priority_level: str = "standard"
    service_type: str = "door_to_door"

    # Fix Pass 2 item C. Not expected as caller input for a fresh import
    # (defaults to PENDING like the ORM column) -- present mainly so an
    # import can carry a status column when re-importing already-planned
    # data, and so `get_planning_instance`'s carryover logic has something
    # to update.
    status: str = "PENDING"

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in PARCEL_STATUSES:
            raise ValueError(f"status must be one of {sorted(PARCEL_STATUSES)}")
        return value

    @field_validator("time_window_start", "time_window_end")
    @classmethod
    def validate_hhmm(cls, value: str):
        if len(value) != 5 or value[2] != ":":
            raise ValueError("Time must be HH:MM")
        h, m = map(int, value.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("Invalid HH:MM")
        return value

    @field_validator("priority_level")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in PRIORITY_LEVELS:
            raise ValueError(f"priority_level must be one of {sorted(PRIORITY_LEVELS)}")
        return value


class ParcelResponse(ParcelIn):
    cluster_id: Optional[int] = None
    cluster_probability: Optional[float] = None
    is_noise: bool = False
    special_handling: bool = False


class ClusterPredictionRequest(BaseModel):
    parcel: ParcelIn


class ImportError_(BaseModel):
    row: int
    field: str
    reason: str


class CSVUploadResponse(BaseModel):
    dataset_id: str
    inserted: int
    updated: int = 0
    skipped: int
    failed: int = 0
    processed: int = 0
    total_rows: int = 0
    duplicates_removed: int = 0
    dimensions_imputed_count: int = 0
    errors: list[ImportError_] = Field(default_factory=list)
    warnings: list[ImportError_] = Field(default_factory=list)
