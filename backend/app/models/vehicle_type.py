"""Vehicle type catalog.

Satisfies FR03/SO3: the NSGA-II optimizer (Phase 3) must source vehicle
capacities and costs from this table at runtime, never from a literal in
`app/services/` or `app/optimization/`. Capacities can then be changed,
audited and varied per depot without a code deploy, and every load plan can
record the exact snapshot it was optimized against (reproducibility).
"""
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String
from app.db.database import Base
from app.utils_datetime import utcnow


class VehicleTypeCatalog(Base):
    __tablename__ = "vehicle_type_catalog"

    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, index=True, nullable=False)
    display_name = Column(String(128), nullable=False)

    capacity_kg = Column(Float, nullable=False)
    capacity_m3 = Column(Float, nullable=False)
    cargo_length_cm = Column(Float, nullable=False)
    cargo_width_cm = Column(Float, nullable=False)
    cargo_height_cm = Column(Float, nullable=False)
    max_parcels = Column(Integer, nullable=False)
    max_stack_layers = Column(Integer, nullable=False, default=1)

    fixed_cost = Column(Float, nullable=False, default=0.0)
    cost_per_km = Column(Float, nullable=False, default=0.0)
    avg_speed_kmh = Column(Float, nullable=False, default=30.0)

    is_refrigerated = Column(Boolean, default=False, nullable=False)
    temp_min_celsius = Column(Float, nullable=True)
    temp_max_celsius = Column(Float, nullable=True)
    is_hazmat_certified = Column(Boolean, default=False, nullable=False)
    has_tail_lift = Column(Boolean, default=False, nullable=False)

    # Narrow-lane eligibility, not enforced as a constraint yet — reserved
    # for a future access-restriction feature.
    min_road_width_m = Column(Float, nullable=True)

    depot_id = Column(String(32), nullable=True)  # null = available at every depot
    is_active = Column(Boolean, default=True, nullable=False)

    # "placeholder" for seeded rows whose figures are not yet real Sri
    # Lankan capacity/cost data. Cleared (set to null) once a row is
    # confirmed against real figures.
    source = Column(String(32), nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
