from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String
from app.db.database import Base

class VehicleCapability(Base):
    """A reusable vehicle *type* definition (e.g. "Bajaj Three Wheeler") describing
    what it can carry. Not a physical vehicle — Registered Vehicles will reference
    this by id once that feature exists."""

    __tablename__ = "vehicle_capabilities"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), unique=True, index=True, nullable=False)
    category = Column(String(64), nullable=False)
    brand = Column(String(64), nullable=True)
    model = Column(String(64), nullable=True)

    max_weight_kg = Column(Float, nullable=False)
    max_length_cm = Column(Float, nullable=False)
    max_width_cm = Column(Float, nullable=False)
    max_height_cm = Column(Float, nullable=False)

    status = Column(String(16), nullable=False, default="ACTIVE")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    @property
    def max_volume_m3(self) -> float:
        return (self.max_length_cm / 100) * (self.max_width_cm / 100) * (self.max_height_cm / 100)
