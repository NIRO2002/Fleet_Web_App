from datetime import datetime
from beanie import Document, Indexed
from pydantic import Field
from app.utils_datetime import utcnow

class VehicleCapability(Document):
    capability_id: Indexed(int, unique=True)
    name: Indexed(str, unique=True)
    category: str
    brand: str | None = None
    model: str | None = None
    max_weight_kg: float
    max_length_cm: float
    max_width_cm: float
    max_height_cm: float
    status: str = "ACTIVE"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    @property
    def max_volume_m3(self) -> float:
        return (self.max_length_cm / 100) * (self.max_width_cm / 100) * (self.max_height_cm / 100)
    class Settings:
        name = "vehicle_capabilities"
