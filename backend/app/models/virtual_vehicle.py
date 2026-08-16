"""VirtualVehicle model.

A vehicle *slot* materialised by one NSGA-II run (Phase 3/4): a real vehicle
type from `vehicle_type_catalog` loaded with a subset of one planning
instance's parcels. `plan_id` groups every VirtualVehicle produced by the
same pipeline run.
"""
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String
from app.db.database import Base
from app.utils_datetime import utcnow


class VirtualVehicle(Base):
    __tablename__ = "virtual_vehicles"

    id = Column(Integer, primary_key=True)
    virtual_vehicle_id = Column(String(64), unique=True, index=True, nullable=False)

    depot_id = Column(String(32), index=True, nullable=True)
    delivery_date = Column(Date, index=True, nullable=True)
    plan_id = Column(String(64), ForeignKey("load_plans.plan_id"), index=True, nullable=True)

    vehicle_type = Column(String(32), nullable=False)
    capacity_kg = Column(Float, nullable=False)
    capacity_m3 = Column(Float, nullable=False)

    used_weight_kg = Column(Float, default=0, nullable=False)
    used_volume_m3 = Column(Float, default=0, nullable=False)
    parcel_count = Column(Integer, default=0, nullable=False)
    max_parcels = Column(Integer, nullable=True)

    estimated_distance_km = Column(Float, default=0.0, nullable=False)
    time_window_compliance = Column(Float, nullable=True)
    fleet_cost = Column(Float, nullable=True)

    is_refrigerated = Column(Boolean, default=False, nullable=False)
    is_hazmat_certified = Column(Boolean, default=False, nullable=False)

    cargo_length_cm = Column(Float, nullable=True)
    cargo_width_cm = Column(Float, nullable=True)
    cargo_height_cm = Column(Float, nullable=True)

    cluster_id = Column(Integer, nullable=True)
    destination_latitude = Column(Float, nullable=True)
    destination_longitude = Column(Float, nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
