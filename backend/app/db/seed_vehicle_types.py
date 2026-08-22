"""Idempotently seed the vehicle_type_catalog table (FR03/SO3).

Fix Pass 2 item A replaced the four placeholder rows with ten real Sri
Lankan vehicle types -- seven sourced from field data (`source="field_data"`)
plus three refrigerated variants of VAN_MED/TRUCK_2T/TRUCK_4T. Fix Pass 3
G1 dropped the three reefer variants: refrigeration (and hazmat) never
appeared in any Specific Objective or Functional Requirement of the
proposal -- this is commercial last-mile delivery, not cold chain -- so
carrying three catalog rows whose capacities/costs were themselves only
estimates (never field data) no longer earned their keep. The catalog is
the 7 field-data rows only. `seed_vehicle_types()` deactivates the three
dropped codes if a local dev DB already has them seeded from before. See
docs/DESIGN_DECISIONS.md.

`cost_per_trip_reference` is a bundled per-trip quote from the source data
(e.g. "typical fare for a normal-distance job"). It is stored for provenance
only and is NEVER read by the objective function -- `fixed_cost` and
`cost_per_km` already fully determine cost, and adding the bundled quote on
top would double-count the same trip. See docs/DESIGN_DECISIONS.md.

`max_parcels` is not present in the source table (only weight/volume
capacity are). It is derived here as a rough, documented parcel-count cap
scaled from each vehicle's capacity_m3 (heavier/larger vehicles carry more,
smaller parcels per unit volume, so the parcels-per-m3 ratio declines as
vehicles get bigger) -- an engineering estimate, not field data, and not
expected to bind before weight/volume/dimensional constraints do.
"""
import asyncio
from app.db.database import init_database
from app.schemas.vehicle_type import VehicleTypeCatalogIn
from app.services.vehicle_catalog_service import deactivate_type, upsert_type

FIELD_DATA_VEHICLE_TYPES = [
    VehicleTypeCatalogIn(
        code="BIKE",
        display_name="Delivery Scooter/Bike",
        model_name="Honda Dio / TVS HLX",
        capacity_kg=25.0,
        capacity_m3=0.07,
        cargo_length_cm=45.0,
        cargo_width_cm=45.0,
        cargo_height_cm=45.0,
        max_parcels=6,
        max_stack_layers=1,
        fixed_cost=180.0,
        cost_per_km=55.0,
        cost_per_trip_reference=400.0,
        gross_vehicle_weight_kg=240.0,
        vehicle_max_stack_weight_kg=10.0,
        avg_speed_kmh=35.0,
        max_speed_kmh=65.0,
        is_refrigerated=False,
        is_hazmat_certified=False,
        has_tail_lift=False,
        available_from="06:00",
        available_until="23:00",
        source_reference="PickMe Flash / Uber",
        source="field_data",
    ),
    VehicleTypeCatalogIn(
        code="APE_CARGO",
        display_name="Piaggio Ape Cargo",
        model_name="Piaggio Ape Xtra LDX",
        capacity_kg=496.0,
        capacity_m3=2.90,
        cargo_length_cm=166.0,
        cargo_width_cm=140.0,
        cargo_height_cm=125.0,
        max_parcels=60,
        max_stack_layers=2,
        fixed_cost=400.0,
        cost_per_km=95.0,
        cost_per_trip_reference=950.0,
        gross_vehicle_weight_kg=975.0,
        vehicle_max_stack_weight_kg=200.0,
        avg_speed_kmh=35.0,
        max_speed_kmh=50.0,
        is_refrigerated=False,
        is_hazmat_certified=False,
        has_tail_lift=False,
        available_from="06:00",
        available_until="22:00",
        source_reference="Piaggio Lanka",
        source="field_data",
    ),
    VehicleTypeCatalogIn(
        code="TVS_KING",
        display_name="TVS King Kargo",
        model_name="TVS King Kargo HD",
        capacity_kg=450.0,
        capacity_m3=3.40,
        cargo_length_cm=200.0,
        cargo_width_cm=149.0,
        cargo_height_cm=115.0,
        max_parcels=70,
        max_stack_layers=2,
        fixed_cost=350.0,
        cost_per_km=85.0,
        cost_per_trip_reference=850.0,
        gross_vehicle_weight_kg=998.0,
        vehicle_max_stack_weight_kg=180.0,
        avg_speed_kmh=40.0,
        max_speed_kmh=60.0,
        is_refrigerated=False,
        is_hazmat_certified=False,
        has_tail_lift=False,
        available_from="06:00",
        available_until="22:00",
        source_reference="TVS Lanka",
        source="field_data",
    ),
    VehicleTypeCatalogIn(
        code="MICRO_VAN",
        display_name="Micro/Small Van",
        model_name="Suzuki Every (DA17V)",
        capacity_kg=350.0,
        capacity_m3=2.98,
        cargo_length_cm=182.0,
        cargo_width_cm=132.0,
        cargo_height_cm=124.0,
        max_parcels=55,
        max_stack_layers=3,
        fixed_cost=1000.0,
        cost_per_km=120.0,
        cost_per_trip_reference=2500.0,
        gross_vehicle_weight_kg=1300.0,
        vehicle_max_stack_weight_kg=250.0,
        avg_speed_kmh=40.0,
        max_speed_kmh=70.0,
        is_refrigerated=False,
        is_hazmat_certified=False,
        has_tail_lift=False,
        available_from="07:00",
        available_until="19:00",
        source_reference="JDM Spec Sheet",
        source="field_data",
    ),
    VehicleTypeCatalogIn(
        code="VAN_MED",
        display_name="Medium Commercial Van",
        model_name="Toyota HiAce / Nissan KDH",
        capacity_kg=1100.0,
        capacity_m3=6.00,
        cargo_length_cm=293.0,
        cargo_width_cm=154.0,
        cargo_height_cm=133.0,
        max_parcels=130,
        max_stack_layers=4,
        fixed_cost=2000.0,
        cost_per_km=180.0,
        cost_per_trip_reference=5000.0,
        gross_vehicle_weight_kg=3100.0,
        vehicle_max_stack_weight_kg=500.0,
        avg_speed_kmh=50.0,
        max_speed_kmh=90.0,
        # "Optional (Chiller)" in the source data -- modelled as a separate
        # reefer catalog row (VAN_MED_REEFER) rather than a boolean here.
        # See docs/DESIGN_DECISIONS.md decision 1.
        is_refrigerated=False,
        # "Limited" hazmat capability in the source data -- not a modellable
        # boolean state; read conservatively as not certified. See
        # docs/DESIGN_DECISIONS.md decision 2.
        is_hazmat_certified=False,
        has_tail_lift=False,
        available_from="06:00",
        available_until="20:00",
        source_reference="Local Freight Operators",
        source="field_data",
    ),
    VehicleTypeCatalogIn(
        code="TRUCK_2T",
        display_name="Light Commercial Truck (2T)",
        model_name="Isuzu Elf (NKR/NPR)",
        capacity_kg=2500.0,
        capacity_m3=12.48,
        cargo_length_cm=365.0,
        cargo_width_cm=190.0,
        cargo_height_cm=180.0,
        max_parcels=250,
        max_stack_layers=5,
        fixed_cost=3500.0,
        cost_per_km=250.0,
        cost_per_trip_reference=8500.0,
        gross_vehicle_weight_kg=5500.0,
        vehicle_max_stack_weight_kg=1200.0,
        avg_speed_kmh=45.0,
        max_speed_kmh=80.0,
        is_refrigerated=False,
        is_hazmat_certified=True,
        has_tail_lift=False,
        available_from="06:00",
        available_until="18:00",
        source_reference="Isuzu Lanka / Tariff",
        source="field_data",
    ),
    VehicleTypeCatalogIn(
        code="TRUCK_4T",
        display_name="Medium Duty Truck (4T)",
        model_name="Isuzu Forward / Hino 300",
        capacity_kg=4500.0,
        capacity_m3=24.02,
        cargo_length_cm=520.0,
        cargo_width_cm=220.0,
        cargo_height_cm=210.0,
        max_parcels=420,
        max_stack_layers=6,
        fixed_cost=6000.0,
        cost_per_km=380.0,
        cost_per_trip_reference=16000.0,
        gross_vehicle_weight_kg=8500.0,
        vehicle_max_stack_weight_kg=2500.0,
        avg_speed_kmh=40.0,
        max_speed_kmh=70.0,
        is_refrigerated=False,
        is_hazmat_certified=True,
        has_tail_lift=False,
        available_from="05:00",
        available_until="19:00",
        source_reference="Transport Operator Data",
        source="field_data",
    ),
]

VEHICLE_TYPES = FIELD_DATA_VEHICLE_TYPES

# Dropped in Fix Pass 3 G1 (hazmat/refrigeration descoped -- see module
# docstring). Deactivated, not deleted, on seed: any local dev DB that
# already has these rows from before must stop offering them to the
# optimizer without silently losing the historical data.
_DEACTIVATED_CODES = ["VAN_MED_REEFER", "TRUCK_2T_REEFER", "TRUCK_4T_REEFER"]


async def seed_vehicle_types() -> None:
    client = await init_database()
    try:
        for payload in VEHICLE_TYPES:
            await upsert_type(payload)
        for code in _DEACTIVATED_CODES:
            await deactivate_type(code)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(seed_vehicle_types())
    print(f"Seeded {len(VEHICLE_TYPES)} vehicle types.")
