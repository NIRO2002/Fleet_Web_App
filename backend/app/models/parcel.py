"""Parcel model.

Satisfies FR01 (parcel ingestion) and FR02 (constraint-aware preprocessing):
carries every physical and handling attribute the NSGA-II assignment problem
(Phase 3) must enforce as a constraint, plus the (depot_id, delivery_date)
planning-instance key required by SO1/SO2 (bounded, reproducible clustering
and assignment runs instead of an unscoped table scan).
"""
from sqlalchemy import Boolean, Column, Date, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import column_property
from app.db.database import Base
from app.utils_datetime import utcnow

PRIORITY_LEVELS = {"standard", "next_day", "express", "same_day"}


class Parcel(Base):
    __tablename__ = "parcels"

    id = Column(Integer, primary_key=True)
    parcel_id = Column(String(64), unique=True, index=True, nullable=False)

    # Planning-instance key (Phase 2 clustering and Phase 3 optimization
    # operate on exactly one (depot_id, delivery_date) subset at a time).
    depot_id = Column(String(32), index=True, nullable=True)
    delivery_date = Column(Date, index=True, nullable=True)

    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    weight_kg = Column(Float, nullable=False)
    volume_m3 = Column(Float, nullable=False)

    time_window_start = Column(String(5), nullable=False)
    time_window_end = Column(String(5), nullable=False)
    fragile = Column(Boolean, default=False, nullable=False)

    # Dimensional fit (constraint 4 in Phase 3).
    length_cm = Column(Float, nullable=True)
    width_cm = Column(Float, nullable=True)
    height_cm = Column(Float, nullable=True)
    # True if the importer had to impute a cube from volume_m3 because
    # length/width/height were absent (F12) -- a real parcel's true
    # dimensions can be far from a cube (e.g. long and thin), so downstream
    # dimensional-fit checks apply a safety factor to imputed sides rather
    # than trusting them at face value.
    dimensions_imputed = Column(Boolean, default=False, nullable=False)

    # Stacking feasibility (constraint 7).
    stackable = Column(Boolean, default=True, nullable=False)
    max_stack_weight_kg = Column(Float, default=0.0, nullable=False)
    loading_orientation_fixed = Column(Boolean, default=False, nullable=False)

    # Hazmat / refrigeration (constraints 5 and 6).
    hazardous = Column(Boolean, default=False, nullable=False)
    hazmat_class = Column(String(16), nullable=True)
    requires_refrigeration = Column(Boolean, default=False, nullable=False)
    temp_min_celsius = Column(Float, nullable=True)
    temp_max_celsius = Column(Float, nullable=True)

    # Handling flags (feed placement heuristic, Phase 3.5).
    two_person_lift = Column(Boolean, default=False, nullable=False)
    do_not_tilt = Column(Boolean, default=False, nullable=False)

    priority_level = Column(String(16), default="standard", nullable=False)
    service_type = Column(String(24), default="door_to_door", nullable=False)

    # HDBSCAN noise flag (Phase 2). True if this parcel's original cluster
    # label was -1 before noise-handling reassigned it to a real cluster id.
    is_noise = Column(Boolean, default=False, nullable=False)

    cluster_id = Column(Integer, nullable=True)
    cluster_probability = Column(Float, nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)

    # Computed (not stored): hazardous OR requires_refrigeration OR
    # two_person_lift. A SQL-expression column_property so it can never
    # drift from the source flags it is derived from, and stays
    # queryable/orderable like a real column.
    special_handling = column_property(hazardous | requires_refrigeration | two_person_lift)

    __table_args__ = (
        Index("ix_parcels_depot_date", "depot_id", "delivery_date"),
    )
