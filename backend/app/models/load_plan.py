"""LoadPlan model.

Satisfies FR04/SO4/SO5: one row per pipeline run (Phase 4), carrying the
aggregate metrics the evaluation harness (Phase 5) and the dissertation's
statistical comparison read back. `catalog_snapshot` (added in Phase 3) is
what makes a plan's vehicle data reproducible after catalog rows change.
"""
from datetime import datetime
from sqlalchemy import Column, DateTime, Date, Float, Integer, String
from app.db.database import Base


class LoadPlan(Base):
    __tablename__ = "load_plans"

    plan_id = Column(String(64), primary_key=True)
    depot_id = Column(String(32), index=True, nullable=False)
    delivery_date = Column(Date, index=True, nullable=False)

    clustering_method = Column(String(16), nullable=False)  # 'hdbscan' | 'kmeans'
    seed = Column(Integer, nullable=False)

    n_parcels = Column(Integer, nullable=False)
    n_vehicles = Column(Integer, nullable=False)
    mean_utilization = Column(Float, nullable=False)
    total_distance_km = Column(Float, nullable=False)
    mean_time_window_compliance = Column(Float, nullable=False)
    total_fleet_cost = Column(Float, nullable=False)
    hypervolume = Column(Float, nullable=True)
    runtime_seconds = Column(Float, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
