"""Idempotently seed the vehicle_type_catalog table (FR03/SO3).

Fix Pass 2 item A: replaces the four placeholder rows with ten real Sri
Lankan vehicle types -- seven sourced from field data (`source="field_data"`)
plus three refrigerated variants of VAN_MED/TRUCK_2T/TRUCK_4T
(`source="estimated_variant"`, since no field data exists for reefer
capacity/cost and the figures here are a documented derivation -- see
docs/DESIGN_DECISIONS.md).

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
from app.db.session import SessionLocal
from app.schemas.vehicle_type import VehicleTypeCatalogIn
from app.services.vehicle_catalog_service import upsert_type

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

# Reefer variants (Fix Pass 2 A.2, decision 1): ~10% volume reduction for
# the chiller unit/insulation, ~50% fixed_cost premium, ~15% cost_per_km
# premium over the base type they're derived from. Estimates, not field
# data -- see docs/DESIGN_DECISIONS.md.
ESTIMATED_VARIANT_VEHICLE_TYPES = [
    VehicleTypeCatalogIn(
        code="VAN_MED_REEFER",
        display_name="Medium Commercial Van (Reefer)",
        model_name="Toyota HiAce / Nissan KDH (Chiller)",
        capacity_kg=1000.0,
        capacity_m3=5.40,
        cargo_length_cm=293.0,
        cargo_width_cm=154.0,
        cargo_height_cm=133.0,
        max_parcels=110,
        max_stack_layers=4,
        fixed_cost=3000.0,
        cost_per_km=210.0,
        gross_vehicle_weight_kg=3100.0,
        vehicle_max_stack_weight_kg=500.0,
        avg_speed_kmh=50.0,
        max_speed_kmh=90.0,
        is_refrigerated=True,
        temp_min_celsius=-18.0,
        temp_max_celsius=8.0,
        is_hazmat_certified=False,
        has_tail_lift=False,
        available_from="06:00",
        available_until="20:00",
        source_reference="Estimated derivation from VAN_MED -- see docs/DESIGN_DECISIONS.md",
        source="estimated_variant",
    ),
    VehicleTypeCatalogIn(
        code="TRUCK_2T_REEFER",
        display_name="Light Commercial Truck (2T, Reefer)",
        model_name="Isuzu Elf (NKR/NPR) (Reefer Box)",
        capacity_kg=2300.0,
        capacity_m3=11.20,
        cargo_length_cm=365.0,
        cargo_width_cm=190.0,
        cargo_height_cm=180.0,
        max_parcels=230,
        max_stack_layers=5,
        fixed_cost=5000.0,
        cost_per_km=290.0,
        gross_vehicle_weight_kg=5500.0,
        vehicle_max_stack_weight_kg=1200.0,
        avg_speed_kmh=45.0,
        max_speed_kmh=80.0,
        is_refrigerated=True,
        temp_min_celsius=-18.0,
        temp_max_celsius=8.0,
        is_hazmat_certified=True,
        has_tail_lift=False,
        available_from="06:00",
        available_until="18:00",
        source_reference="Estimated derivation from TRUCK_2T -- see docs/DESIGN_DECISIONS.md",
        source="estimated_variant",
    ),
    VehicleTypeCatalogIn(
        code="TRUCK_4T_REEFER",
        display_name="Medium Duty Truck (4T, Reefer)",
        model_name="Isuzu Forward / Hino 300 (Reefer Box)",
        capacity_kg=4200.0,
        capacity_m3=21.60,
        cargo_length_cm=520.0,
        cargo_width_cm=220.0,
        cargo_height_cm=210.0,
        max_parcels=380,
        max_stack_layers=6,
        fixed_cost=8500.0,
        cost_per_km=440.0,
        gross_vehicle_weight_kg=8500.0,
        vehicle_max_stack_weight_kg=2500.0,
        avg_speed_kmh=40.0,
        max_speed_kmh=70.0,
        is_refrigerated=True,
        temp_min_celsius=-18.0,
        temp_max_celsius=8.0,
        is_hazmat_certified=True,
        has_tail_lift=False,
        available_from="05:00",
        available_until="19:00",
        source_reference="Estimated derivation from TRUCK_4T -- see docs/DESIGN_DECISIONS.md",
        source="estimated_variant",
    ),
]

VEHICLE_TYPES = FIELD_DATA_VEHICLE_TYPES + ESTIMATED_VARIANT_VEHICLE_TYPES


def seed_vehicle_types() -> None:
    db = SessionLocal()
    try:
        for payload in VEHICLE_TYPES:
            upsert_type(db, payload)
    finally:
        db.close()


if __name__ == "__main__":
    seed_vehicle_types()
    print(f"Seeded {len(VEHICLE_TYPES)} vehicle types.")
