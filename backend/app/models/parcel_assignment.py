"""ParcelAssignment model.

Satisfies FR04/FR05: the association between a load plan, a virtual vehicle
and a parcel that carries the delivery sequence, the reverse (LIFO) load
sequence, and the 3D placement produced by Phase 3's placement heuristic.
This is the row-level detail the CSV/JSON export (Phase 4) is built from.
"""
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from app.db.database import Base
from app.utils_datetime import utcnow


class ParcelAssignment(Base):
    __tablename__ = "parcel_assignments"

    id = Column(Integer, primary_key=True)
    plan_id = Column(String(64), ForeignKey("load_plans.plan_id"), index=True, nullable=False)
    virtual_vehicle_id = Column(
        String(64), ForeignKey("virtual_vehicles.virtual_vehicle_id"), index=True, nullable=False
    )
    parcel_id = Column(String(64), ForeignKey("parcels.parcel_id"), index=True, nullable=False)

    delivery_sequence = Column(Integer, nullable=False)  # 1-based stop order
    load_sequence = Column(Integer, nullable=False)  # 1-based, 1 = loaded first = deepest

    stack_layer = Column(Integer, nullable=False, default=0)
    load_position_x = Column(Float, nullable=False, default=0.0)
    load_position_y = Column(Float, nullable=False, default=0.0)
    load_position_z = Column(Float, nullable=False, default=0.0)
    # Actual oriented box dimensions selected by placement. Parcel source
    # dimensions alone cannot reconstruct a 90-degree floor rotation.
    placed_length_cm = Column(Float, nullable=True)
    placed_width_cm = Column(Float, nullable=True)
    placed_height_cm = Column(Float, nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
