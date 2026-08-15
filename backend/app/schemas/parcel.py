from typing import Optional
from pydantic import BaseModel, Field, field_validator

class ParcelIn(BaseModel):
    parcel_id: str = Field(min_length=1, max_length=64)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    weight_kg: float = Field(gt=0)
    volume_m3: float = Field(gt=0)
    time_window_start: str
    time_window_end: str
    fragile: bool = False

    @field_validator("time_window_start", "time_window_end")
    @classmethod
    def validate_hhmm(cls, value: str):
        if len(value) != 5 or value[2] != ":":
            raise ValueError("Time must be HH:MM")
        h, m = map(int, value.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("Invalid HH:MM")
        return value

class ParcelResponse(ParcelIn):
    cluster_id: Optional[int] = None
    cluster_probability: Optional[float] = None

class ClusterPredictionRequest(BaseModel):
    parcel: ParcelIn

class CSVUploadResponse(BaseModel):
    inserted: int
    skipped: int
