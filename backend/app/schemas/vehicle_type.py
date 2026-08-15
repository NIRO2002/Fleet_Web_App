"""Schemas for the vehicle type catalog (FR03/SO3). See
app/models/vehicle_type.py and app/services/vehicle_catalog_service.py."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class VehicleTypeCatalogIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    display_name: str = Field(min_length=1, max_length=128)

    capacity_kg: float = Field(gt=0)
    capacity_m3: float = Field(gt=0)
    cargo_length_cm: float = Field(gt=0)
    cargo_width_cm: float = Field(gt=0)
    cargo_height_cm: float = Field(gt=0)
    max_parcels: int = Field(gt=0)
    max_stack_layers: int = Field(ge=1, default=1)

    fixed_cost: float = Field(ge=0, default=0.0)
    cost_per_km: float = Field(ge=0, default=0.0)
    avg_speed_kmh: float = Field(gt=0, default=30.0)

    is_refrigerated: bool = False
    temp_min_celsius: Optional[float] = None
    temp_max_celsius: Optional[float] = None
    is_hazmat_certified: bool = False
    has_tail_lift: bool = False

    min_road_width_m: Optional[float] = None
    depot_id: Optional[str] = Field(default=None, max_length=32)
    is_active: bool = True
    source: Optional[str] = Field(default=None, max_length=32)

    @field_validator("code")
    @classmethod
    def uppercase_code(cls, value: str) -> str:
        return value.strip().upper()


class VehicleTypeCatalogResponse(VehicleTypeCatalogIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
