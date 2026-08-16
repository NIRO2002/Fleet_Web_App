"""Phase 0 (Backend Remediation) regression net.

Exercises the pipeline end-to-end through the public HTTP API: ingest
parcels -> train HDBSCAN -> run NSGA-II load assignment -> list the
resulting virtual vehicle(s) -> dynamically insert a parcel. Complements
(does not replace) `test_nsga2.py`'s direct, service-level Phase 3 gate
tests — this one is the only place that exercises the whole thing through
FastAPI routes, so it catches wiring bugs the service-level tests can't.

Originally documented the pre-remediation pipeline's defective behaviour on
purpose; since Phase 3 the assignment problem requires a real
vehicle_type_catalog (it never falls back to a built-in default), so this
test now seeds one, and no longer assumes exactly one virtual vehicle comes
out of one cluster — the new n+K encoding may legitimately split a cluster
across more than one vehicle.
"""
from app.schemas.vehicle_type import VehicleTypeCatalogIn
from app.services import vehicle_catalog_service


def test_full_pipeline_smoke(client, db_session, parcel_factory):
    vehicle_catalog_service.upsert_type(
        db_session,
        VehicleTypeCatalogIn(
            code="VAN", display_name="Delivery van", capacity_kg=1000.0, capacity_m3=8.0,
            cargo_length_cm=280.0, cargo_width_cm=170.0, cargo_height_cm=170.0,
            max_parcels=120, max_stack_layers=4, fixed_cost=2500.0, cost_per_km=45.0,
            avg_speed_kmh=32.0, source="test-fixture",
        ),
    )

    depot_id = "DEPOT-1"
    delivery_date = "2026-08-20"
    parcels = parcel_factory(n=20, seed=1, n_clusters=2, depot_id=depot_id, delivery_date=delivery_date)
    for payload in parcels:
        resp = client.post("/api/v1/parcels", json=payload)
        assert resp.status_code == 200, resp.text

    resp = client.get("/api/v1/parcels")
    assert resp.status_code == 200
    assert len(resp.json()) == len(parcels)

    resp = client.post(
        "/api/v1/parcels/clustering/train",
        params={"depot_id": depot_id, "delivery_date": delivery_date},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "trained"
    assert body["parcel_count"] == len(parcels)

    clusters = body["clusters"]
    real_cluster_ids = sorted(int(k) for k in clusters if k != "-1")
    assert real_cluster_ids, f"expected at least one real cluster, got {clusters}"

    resp = client.get(
        "/api/v1/parcels/clustering",
        params={"depot_id": depot_id, "delivery_date": delivery_date},
    )
    assert resp.status_code == 200
    assert resp.json() == clusters

    cluster_id = real_cluster_ids[0]
    resp = client.post("/api/v1/optimization/run", json={"cluster_id": cluster_id})
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert "selected_vehicle" in result
    assert "pareto_solutions" in result
    assert result["cluster_id"] == cluster_id

    resp = client.get("/api/v1/virtual-vehicles")
    assert resp.status_code == 200
    vehicles = resp.json()
    # A cluster may now legitimately be split across more than one vehicle
    # slot (the n+K encoding, unlike the old one-vehicle-type-for-the-whole
    # -parcel-list defect) — at least one is the real invariant.
    assert len(vehicles) >= 1

    new_parcel = {
        "parcel_id": "P9999",
        "latitude": 6.9271,
        "longitude": 79.8612,
        "weight_kg": 1.0,
        "volume_m3": 0.005,
        "time_window_start": "10:00",
        "time_window_end": "12:00",
        "fragile": False,
    }
    vv_id = vehicles[0]["virtual_vehicle_id"]
    resp = client.post(f"/api/v1/virtual-vehicles/{vv_id}/insert-parcel", json=new_parcel)
    assert resp.status_code == 200, resp.text
    assert "inserted" in resp.json()


def test_csv_upload_smoke(client):
    csv_content = (
        "parcel_id,latitude,longitude,weight_kg,volume_m3,"
        "time_window_start,time_window_end,fragile\n"
        "C001,6.9271,79.8612,2.5,0.015,10:00,13:00,false\n"
        "C002,6.9290,79.8640,3.2,0.020,10:00,13:00,false\n"
    )
    resp = client.post(
        "/api/v1/parcels/upload-csv",
        files={"file": ("parcels.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["inserted"] == 2
    assert body["skipped"] == 0
