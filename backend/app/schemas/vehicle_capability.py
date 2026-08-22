from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

STATUSES = {"ACTIVE", "INACTIVE"}

class VehicleCapabilityIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=64)
    brand: Optional[str] = Field(default=None, max_length=64)
    model: Optional[str] = Field(default=None, max_length=64)
    max_weight_kg: float = Field(gt=0)
    max_length_cm: float = Field(gt=0)
    max_width_cm: float = Field(gt=0)
    max_height_cm: float = Field(gt=0)
    status: str = "ACTIVE"

    @field_validator("name", "category")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("brand", "model")
    @classmethod
    def strip_optional(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        return value or None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in STATUSES:
            raise ValueError(f"status must be one of {sorted(STATUSES)}")
        return value

class VehicleCapabilityResponse(VehicleCapabilityIn):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(validation_alias="capability_id")
    max_volume_m3: float
    created_at: datetime
    updated_at: datetime
