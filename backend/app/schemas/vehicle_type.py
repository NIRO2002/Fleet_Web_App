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

    model_name: Optional[str] = Field(default=None, max_length=128)
    gross_vehicle_weight_kg: Optional[float] = Field(default=None, gt=0)
    # Provenance only -- see app/models/vehicle_type.py docstring on the
    # matching column. Never consumed by the optimizer.
    cost_per_trip_reference: Optional[float] = Field(default=None, ge=0)
    vehicle_max_stack_weight_kg: float = Field(default=1_000_000.0, ge=0)
    max_speed_kmh: Optional[float] = Field(default=None, gt=0)
    available_from: str = "00:00"
    available_until: str = "23:59"
    source_reference: Optional[str] = Field(default=None, max_length=128)

    depot_id: Optional[str] = Field(default=None, max_length=32)
    is_active: bool = True
    source: Optional[str] = Field(default=None, max_length=32)

    @field_validator("code")
    @classmethod
    def uppercase_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("available_from", "available_until")
    @classmethod
    def validate_hhmm(cls, value: str):
        if len(value) != 5 or value[2] != ":":
            raise ValueError("Time must be HH:MM")
        h, m = map(int, value.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("Invalid HH:MM")
        return value


class VehicleTypeCatalogResponse(VehicleTypeCatalogIn):
    model_config = ConfigDict(from_attributes=True)

    created_at: datetime
    updated_at: datetime
