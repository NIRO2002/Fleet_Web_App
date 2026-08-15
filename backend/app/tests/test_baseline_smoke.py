"""Phase 0 (Backend Remediation) regression net.

Exercises the *current* (pre-remediation) pipeline end-to-end through the
public API: ingest parcels -> train HDBSCAN -> run NSGA-II-labelled
optimization -> generate a virtual vehicle -> dynamically insert a parcel.

This file documents the current (defective) behaviour on purpose, so later
phases can detect accidental regressions while rewriting the internals. It
is allowed to be deleted once Phase 3's real tests (test_nsga2.py etc.)
replace it, per the remediation spec.
"""


def test_full_pipeline_smoke(client, parcel_factory):
    parcels = parcel_factory(n=20, seed=1, n_clusters=2)
    for payload in parcels:
        resp = client.post("/api/v1/parcels", json=payload)
        assert resp.status_code == 200, resp.text

    resp = client.get("/api/v1/parcels")
    assert resp.status_code == 200
    assert len(resp.json()) == len(parcels)

    resp = client.post("/api/v1/parcels/clustering/train")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "trained"
    assert body["parcel_count"] == len(parcels)

    clusters = body["clusters"]
    real_cluster_ids = sorted(int(k) for k in clusters if k != "-1")
    assert real_cluster_ids, f"expected at least one real cluster, got {clusters}"

    resp = client.get("/api/v1/parcels/clustering")
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
    assert len(vehicles) == 1

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
