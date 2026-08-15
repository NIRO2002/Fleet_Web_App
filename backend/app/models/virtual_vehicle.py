from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String
from app.db.database import Base

class VirtualVehicle(Base):
    __tablename__ = "virtual_vehicles"

    id = Column(Integer, primary_key=True)
    virtual_vehicle_id = Column(String(64), unique=True, index=True, nullable=False)

    vehicle_type = Column(String(32), nullable=False)
    capacity_kg = Column(Float, nullable=False)
    capacity_m3 = Column(Float, nullable=False)

    used_weight_kg = Column(Float, default=0, nullable=False)
    used_volume_m3 = Column(Float, default=0, nullable=False)

    cluster_id = Column(Integer, nullable=True)
    destination_latitude = Column(Float, nullable=True)
    destination_longitude = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
