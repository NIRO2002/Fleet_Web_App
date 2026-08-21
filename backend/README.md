# Fleet Web App Backend

This FastAPI service takes parcels for one depot and delivery date, clusters them into stable geographic density groups with HDBSCAN, selects virtual vehicles from a MongoDB-backed catalog with NSGA-II, and persists a load plan. Urgency and physical attributes remain downstream assignment/loading inputs rather than HDBSCAN similarity features. Each plan contains its virtual vehicles and every parcel's 3D cargo position in LIFO loading order. Physical fleet assignment and final route optimization are downstream responsibilities.

## Setup

Requirements: Python 3.11+ and MongoDB. Start MongoDB directly:

```bash
docker run --name fleet-mongodb -p 27017:27017 -d mongo:8
```

Then install and run the service:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env
python -m app.db.seed_vehicle_types
uvicorn app.main:app --reload
```

On Linux/macOS use `cp .env.example .env`. The supplied `.env.example` targets `mongodb://localhost:27017/` and database `fleet_web_app`. To start MongoDB and the backend together, run `docker compose up --build`.

Interactive OpenAPI documentation is at `http://localhost:8000/docs`. Run verification with `pytest -q`.

## Core workflow

```bash
# Upload CSV data
curl -F "file=@data/parcels_sample_36000.csv" http://localhost:8000/api/v1/parcels/upload-csv

# Cluster one planning instance
curl -X POST "http://localhost:8000/api/v1/parcels/clustering/train?depot_id=D-CMB-001&delivery_date=2026-01-05&seed=0"

# Optimize one cluster (parcel_ids may be supplied instead)
curl -X POST http://localhost:8000/api/v1/optimization/run -H "Content-Type: application/json" -d '{"cluster_id":0}'

# Read/export the returned plan_id
curl http://localhost:8000/api/v1/optimization/plans/PLAN-ID
curl -OJ http://localhost:8000/api/v1/optimization/plans/PLAN-ID/export.csv
```

`POST /optimization/run` returns the selected vehicle set, Pareto solutions, feasibility diagnostics, and `plan_id`. `GET /plans/{plan_id}` returns the complete nested plan tree. The CSV export contains one row per assignment and round-trips the placement and ordering fields.

## API reference

All routes use the `/api/v1` prefix.

| Method and path | Input | Response | Example |
|---|---|---|---|
| `GET /health` | none | health status | `curl localhost:8000/api/v1/health` |
| `POST /auth/login` | placeholder JSON | placeholder auth response | `curl -X POST localhost:8000/api/v1/auth/login` |
| `POST /parcels` | `ParcelIn` JSON | parcel document | `curl -X POST localhost:8000/api/v1/parcels -H "Content-Type: application/json" -d '{"parcel_id":"P1","depot_id":"D1","delivery_date":"2026-01-05","latitude":6.9271,"longitude":79.8612,"weight_kg":2,"volume_m3":0.01,"time_window_start":"09:00","time_window_end":"12:00"}'` |
| `GET /parcels` | optional `depot_id`, `delivery_date` query | parcel list | `curl "localhost:8000/api/v1/parcels?depot_id=D1&delivery_date=2026-01-05"` |
| `POST /parcels/upload-csv` | multipart CSV file | insert/update/error counts | `curl -F "file=@parcels.csv" localhost:8000/api/v1/parcels/upload-csv` |
| `POST /parcels/clustering/train` | depot/date/seed query | cluster audit | `curl -X POST "localhost:8000/api/v1/parcels/clustering/train?depot_id=D1&delivery_date=2026-01-05&seed=0"` |
| `GET /parcels/clustering` | depot/date query | counts by cluster | `curl "localhost:8000/api/v1/parcels/clustering?depot_id=D1&delivery_date=2026-01-05"` |
| `POST /parcels/clustering/predict` | `{"parcel": ParcelIn}` plus depot/date query | predicted cluster | `curl -X POST "localhost:8000/api/v1/parcels/clustering/predict?depot_id=D1&delivery_date=2026-01-05" -H "Content-Type: application/json" -d '{"parcel":{"parcel_id":"P2","latitude":6.92,"longitude":79.86,"weight_kg":1,"volume_m3":0.01,"time_window_start":"09:00","time_window_end":"12:00"}}'` |
| `POST /optimization/run` | `cluster_id` or `parcel_ids` | optimization result and plan ID | `curl -X POST localhost:8000/api/v1/optimization/run -H "Content-Type: application/json" -d '{"parcel_ids":["P1","P2"]}'` |
| `GET /optimization/plans/{plan_id}` | path ID | full embedded plan tree | `curl localhost:8000/api/v1/optimization/plans/PLAN-ID` |
| `GET /optimization/plans/{plan_id}/export.csv` | path ID | CSV assignments | `curl -OJ localhost:8000/api/v1/optimization/plans/PLAN-ID/export.csv` |
| `GET /virtual-vehicles` | none | embedded vehicles from plans | `curl localhost:8000/api/v1/virtual-vehicles` |
| `POST /virtual-vehicles/{id}/insert-parcel` | `ParcelIn` JSON | fit result and remaining capacity | `curl -X POST localhost:8000/api/v1/virtual-vehicles/VV-ID/insert-parcel -H "Content-Type: application/json" -d '{"parcel_id":"P3","latitude":6.92,"longitude":79.86,"weight_kg":1,"volume_m3":0.01,"time_window_start":"09:00","time_window_end":"12:00"}'` |
| `GET /vehicle-types` | optional `depot_id` | active catalog rows | `curl "localhost:8000/api/v1/vehicle-types?depot_id=D1"` |
| `GET /vehicle-types/{code}` | catalog code | catalog row | `curl localhost:8000/api/v1/vehicle-types/TRUCK_4T` |
| `POST /vehicle-types` | `VehicleTypeCatalogIn` JSON | created row | `curl -X POST localhost:8000/api/v1/vehicle-types -H "Content-Type: application/json" --data @vehicle-type.json` |
| `PATCH /vehicle-types/{code}` | complete `VehicleTypeCatalogIn` JSON | updated row | `curl -X PATCH localhost:8000/api/v1/vehicle-types/TRUCK_4T -H "Content-Type: application/json" --data @vehicle-type.json` |
| `DELETE /vehicle-types/{code}` | path code | 204; deactivates row | `curl -X DELETE localhost:8000/api/v1/vehicle-types/TRUCK_4T` |
| `GET /vehicle-capabilities` | optional `status` | capability list | `curl "localhost:8000/api/v1/vehicle-capabilities?status=ACTIVE"` |
| `GET /vehicle-capabilities/{id}` | numeric ID | capability | `curl localhost:8000/api/v1/vehicle-capabilities/1` |
| `POST /vehicle-capabilities` | `VehicleCapabilityIn` JSON | created capability | `curl -X POST localhost:8000/api/v1/vehicle-capabilities -H "Content-Type: application/json" -d '{"name":"Van","category":"VAN","max_weight_kg":1000,"max_length_cm":280,"max_width_cm":170,"max_height_cm":170}'` |
| `PUT /vehicle-capabilities/{id}` | complete `VehicleCapabilityIn` JSON | updated capability | `curl -X PUT localhost:8000/api/v1/vehicle-capabilities/1 -H "Content-Type: application/json" --data @capability.json` |
| `DELETE /vehicle-capabilities/{id}` | numeric ID | 204 | `curl -X DELETE localhost:8000/api/v1/vehicle-capabilities/1` |

The integration placeholders `GET /vehicles/status`, `/maintenance/status`, `/predictions/status`, `/demand/status`, `/deliveries/status`, `/routes/status`, `/trips/status`, `/alerts/status`, and `/reports/status` return a lightweight module status. Example: `curl localhost:8000/api/v1/vehicles/status`; substitute each listed module name to test every placeholder.

## MongoDB data model

- `parcels`: independently queried parcel documents. A compound `(depot_id, delivery_date)` index scopes planning instances; `status` and unique `parcel_id` are indexed.
- `vehicle_type_catalog`: seven seeded optimizer vehicle types, uniquely indexed by `code`.
- `load_plans`: aggregate metrics, catalog/run snapshots, and embedded virtual vehicles. Every virtual vehicle embeds its parcel assignments and 3D placement.
- `vehicle_capabilities`: the separate team-owned capability catalog.

## Integration notes

- `delivery_sequence` is a nearest-neighbour estimate used to construct a feasible load order. It is not an optimized route; the downstream route optimizer owns stop reordering.
- `load_sequence` is the reverse loading order. Placement coordinates and oriented dimensions drive the frontend 3D cargo view.
- The optimizer is CPU-bound and runs in a worker thread, so other FastAPI requests remain responsive.
- Vehicle capacities and costs always come from `vehicle_type_catalog`; load plans retain a catalog snapshot for reproducibility.
