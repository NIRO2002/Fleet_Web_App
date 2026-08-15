from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String
from app.db.database import Base

class Parcel(Base):
    __tablename__ = "parcels"

    id = Column(Integer, primary_key=True)
    parcel_id = Column(String(64), unique=True, index=True, nullable=False)

    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    weight_kg = Column(Float, nullable=False)
    volume_m3 = Column(Float, nullable=False)

    time_window_start = Column(String(5), nullable=False)
    time_window_end = Column(String(5), nullable=False)
    fragile = Column(Boolean, default=False, nullable=False)

    cluster_id = Column(Integer, nullable=True)
    cluster_probability = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
