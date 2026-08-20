import csv
import io
from datetime import date

from app.models.load_plan import LoadPlan
from app.models.parcel import Parcel
from app.models.parcel_assignment import ParcelAssignment
from app.models.virtual_vehicle import VirtualVehicle


def _seed_plan(db_session):
    plan = LoadPlan(
        plan_id="PLAN-EXPORT", depot_id="D-CMB-001", delivery_date=date(2026, 1, 5),
        clustering_method="hdbscan", seed=0, n_parcels=1, n_vehicles=1,
        mean_utilization=0.42, total_distance_km=12.5,
        mean_time_window_compliance=1.0, total_fleet_cost=10000.0,
        runtime_seconds=3.2,
    )
    parcel = Parcel(
        parcel_id="P-EXPORT", depot_id="D-CMB-001", delivery_date=date(2026, 1, 5),
        latitude=6.9, longitude=79.8, weight_kg=12.5, volume_m3=0.08,
        length_cm=50, width_cm=40, height_cm=30,
        time_window_start="08:00", time_window_end="12:00",
        fragile=False, stackable=True, max_stack_weight_kg=10,
    )
    vehicle = VirtualVehicle(
        virtual_vehicle_id="VV-EXPORT", plan_id=plan.plan_id, depot_id=plan.depot_id,
        delivery_date=plan.delivery_date, vehicle_type="TRUCK_4T",
        capacity_kg=4500, capacity_m3=24.02, used_weight_kg=12.5,
        used_volume_m3=0.08, parcel_count=1, cargo_length_cm=520,
        cargo_width_cm=220, cargo_height_cm=210,
    )
    assignment = ParcelAssignment(
        plan_id=plan.plan_id, virtual_vehicle_id=vehicle.virtual_vehicle_id,
        parcel_id=parcel.parcel_id, delivery_sequence=1, load_sequence=1,
        stack_layer=0, load_position_x=10, load_position_y=20, load_position_z=0,
    )
    db_session.add_all([plan, parcel, vehicle, assignment])
    db_session.commit()


def test_load_plan_json_is_nested_and_complete(client, db_session):
    _seed_plan(db_session)
    response = client.get("/api/v1/optimization/plans/PLAN-EXPORT")
    assert response.status_code == 200
    body = response.json()
    assert body["plan_id"] == "PLAN-EXPORT"
    assert body["vehicles"][0]["cargo_length_cm"] == 520
    assert body["vehicles"][0]["parcels"][0] == {
        "parcel_id": "P-EXPORT", "delivery_sequence": 1, "load_sequence": 1,
        "stack_layer": 0, "load_position_x": 10.0, "load_position_y": 20.0,
        "load_position_z": 0.0, "length_cm": 50.0, "width_cm": 40.0,
        "height_cm": 30.0, "weight_kg": 12.5, "volume_m3": 0.08,
        "fragile": False, "stackable": True, "time_window_start": "08:00",
        "time_window_end": "12:00",
    }


def test_csv_round_trip_preserves_assignment_fields(client, db_session):
    _seed_plan(db_session)
    response = client.get("/api/v1/optimization/plans/PLAN-EXPORT/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 1
    row = rows[0]
    assert row["plan_id"] == "PLAN-EXPORT"
    assert row["virtual_vehicle_id"] == "VV-EXPORT"
    assert row["parcel_id"] == "P-EXPORT"
    assert int(row["delivery_sequence"]) == 1
    assert int(row["load_sequence"]) == 1
    assert int(row["stack_layer"]) == 0
    assert float(row["load_position_x"]) == 10.0


def test_missing_plan_returns_404(client):
    assert client.get("/api/v1/optimization/plans/DOES-NOT-EXIST").status_code == 404
    assert client.get("/api/v1/optimization/plans/DOES-NOT-EXIST/export.csv").status_code == 404
