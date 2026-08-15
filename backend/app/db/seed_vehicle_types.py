"""Idempotently seed the vehicle_type_catalog table (FR03/SO3).

These four rows carry the same capacity figures as the old hardcoded
`optimization_service.VEHICLES` dict, plus placeholder cargo dimensions,
cost and speed figures invented only to make the optimizer runnable end to
end. Every row is marked source="placeholder" — replace with real Sri
Lankan capacity/cost figures before final dissertation results are
reported (see docs/DESIGN_DECISIONS.md).
"""
from app.db.session import SessionLocal
from app.schemas.vehicle_type import VehicleTypeCatalogIn
from app.services.vehicle_catalog_service import upsert_type

PLACEHOLDER_VEHICLE_TYPES = [
    VehicleTypeCatalogIn(
        code="BIKE",
        display_name="Motorbike with delivery box",
        capacity_kg=25.0,
        capacity_m3=0.08,
        cargo_length_cm=40.0,
        cargo_width_cm=35.0,
        cargo_height_cm=35.0,
        max_parcels=8,
        max_stack_layers=2,
        fixed_cost=500.0,
        cost_per_km=15.0,
        avg_speed_kmh=28.0,
        has_tail_lift=False,
        source="placeholder",
    ),
    VehicleTypeCatalogIn(
        code="THREE_WHEEL",
        display_name="Three-wheeler (trishaw)",
        capacity_kg=150.0,
        capacity_m3=0.8,
        cargo_length_cm=110.0,
        cargo_width_cm=90.0,
        cargo_height_cm=90.0,
        max_parcels=25,
        max_stack_layers=3,
        fixed_cost=900.0,
        cost_per_km=22.0,
        avg_speed_kmh=24.0,
        has_tail_lift=False,
        source="placeholder",
    ),
    VehicleTypeCatalogIn(
        code="VAN",
        display_name="Delivery van",
        capacity_kg=1000.0,
        capacity_m3=8.0,
        cargo_length_cm=280.0,
        cargo_width_cm=170.0,
        cargo_height_cm=170.0,
        max_parcels=120,
        max_stack_layers=4,
        fixed_cost=2500.0,
        cost_per_km=45.0,
        avg_speed_kmh=32.0,
        is_refrigerated=False,
        has_tail_lift=True,
        source="placeholder",
    ),
    VehicleTypeCatalogIn(
        code="LORRY",
        display_name="Lorry (rigid truck)",
        capacity_kg=5000.0,
        capacity_m3=25.0,
        cargo_length_cm=550.0,
        cargo_width_cm=220.0,
        cargo_height_cm=220.0,
        max_parcels=400,
        max_stack_layers=5,
        fixed_cost=6000.0,
        cost_per_km=85.0,
        avg_speed_kmh=28.0,
        has_tail_lift=True,
        source="placeholder",
    ),
]


def seed_vehicle_types() -> None:
    db = SessionLocal()
    try:
        for payload in PLACEHOLDER_VEHICLE_TYPES:
            upsert_type(db, payload)
    finally:
        db.close()


if __name__ == "__main__":
    seed_vehicle_types()
    print(f"Seeded {len(PLACEHOLDER_VEHICLE_TYPES)} placeholder vehicle types.")
