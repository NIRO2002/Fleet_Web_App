"""LoadPlan model.

Satisfies FR04/SO4/SO5: one row per pipeline run (Phase 4), carrying the
aggregate metrics the evaluation harness (Phase 5) and the dissertation's
statistical comparison read back. `catalog_snapshot` (added in Phase 3) is
what makes a plan's vehicle data reproducible after catalog rows change.
"""
from sqlalchemy import JSON, Column, DateTime, Date, Float, Integer, String
from app.db.database import Base
from app.utils_datetime import utcnow


class LoadPlan(Base):
    __tablename__ = "load_plans"

    plan_id = Column(String(64), primary_key=True)
    depot_id = Column(String(32), index=True, nullable=False)
    delivery_date = Column(Date, index=True, nullable=False)

    clustering_method = Column(String(16), nullable=False)  # 'hdbscan' | 'kmeans'
    seed = Column(Integer, nullable=False)

    # Exact vehicle_type_catalog rows this plan was optimized against
    # (list of VehicleTypeSpec fields, as dicts) — reproducibility: catalog
    # rows can change after the fact, but the plan still records what the
    # optimizer actually saw (Phase 3.1).
    catalog_snapshot = Column(JSON, nullable=True)

    n_parcels = Column(Integer, nullable=False)
    n_vehicles = Column(Integer, nullable=False)
    # How many of this plan's parcels had imputed (cube-from-volume, not
    # measured) dimensions (F12) -- so a plan built on imputed data is
    # identifiable after the fact, since imputed dimensions get a safety
    # factor that biases the plan conservative, not exact.
    n_parcels_with_imputed_dimensions = Column(Integer, nullable=False, default=0)
    # Fix Pass 2 item C: how many of this plan's parcels were rolled forward
    # from an earlier delivery_date (Parcel.carried_over_from_date is set).
    n_carryover_parcels = Column(Integer, nullable=False, default=0)
    # DRAFT | PUBLISHED | CLOSED. Only DRAFT is set by this pass -- no
    # transition trigger for PUBLISHED/CLOSED exists yet (out of scope).
    status = Column(String(16), nullable=False, default="DRAFT")
    # Fix Pass 2 item E: reproducibility snapshot (git commit, package
    # versions, settings) captured at the moment this plan was optimized.
    run_manifest = Column(JSON, nullable=True)
    mean_utilization = Column(Float, nullable=False)
    total_distance_km = Column(Float, nullable=False)
    mean_time_window_compliance = Column(Float, nullable=False)
    total_fleet_cost = Column(Float, nullable=False)
    hypervolume = Column(Float, nullable=True)
    runtime_seconds = Column(Float, nullable=False)

    created_at = Column(DateTime, default=utcnow, nullable=False)
