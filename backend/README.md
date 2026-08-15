# Fleet Web App Backend

This backend follows the exact structure shared by the colleague:

```text
Fleet_Web_App/backend/
├── app/
│   ├── api/
│   │   ├── v1/
│   │   ├── deps.py
│   ├── core/
│   ├── db/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   ├── ml_placeholders/
│   ├── routing/
│   ├── realtime/
│   ├── tests/
│   └── main.py
├── alembic/
├── .env.example
├── pyproject.toml
├── Dockerfile
└── README.md
```

## Research component implemented

```text
Parcels
  ↓
Preprocessing
  ↓
HDBSCAN
  ↓
Parcel clusters
  ↓
NSGA-II
  ├── maximize load utilization
  ├── minimize distance
  └── maximize time-window compliance
  ↓
Virtual vehicle type
  ├── BIKE
  ├── THREE_WHEEL
  ├── VAN
  └── LORRY
  ↓
Virtual load
  ↓
Dynamic new-parcel insertion
```

**Real Fleet Optimization is intentionally excluded.**

## Endpoints

### Parcels
- `POST /api/v1/parcels`
- `GET /api/v1/parcels`
- `POST /api/v1/parcels/upload-csv`

### HDBSCAN
- `POST /api/v1/parcels/clustering/train`
- `GET /api/v1/parcels/clustering`
- `POST /api/v1/parcels/clustering/predict`

### NSGA-II
- `POST /api/v1/optimization/run`

### Virtual vehicles
- `GET /api/v1/virtual-vehicles`
- `POST /api/v1/virtual-vehicles/{virtual_vehicle_id}/insert-parcel`

### Shared fleet placeholders
The files `auth.py`, `vehicles.py`, `maintenance.py`, `predictions.py`,
`demand.py`, `deliveries.py`, `routes.py`, `trips.py`, `alerts.py`,
and `reports.py` are intentionally kept as lightweight placeholders so
your colleague can merge their real fleet implementations without changing
your research module.

## Run locally

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

pip install -e ".[dev]"

uvicorn app.main:app --reload
```

Swagger:
`http://127.0.0.1:8000/docs`

## CSV format

```text
parcel_id,latitude,longitude,weight_kg,volume_m3,time_window_start,time_window_end,fragile
P001,6.9271,79.8612,2.5,0.015,10:00,13:00,false
```

## Research notes

HDBSCAN is used to discover parcel clusters. NSGA-II is used for multi-objective
selection of a feasible virtual vehicle/load configuration.

The current distance function is a haversine + nearest-neighbor approximation.
For the final research implementation, it should be replaced with a road-network
matrix from OSRM/GraphHopper/OpenRouteService if actual road distance is required.

The vehicle capacities are prototype values and must be replaced with the final
values agreed for your dataset/research.

## Important integration boundary

Your research component should return a virtual load such as:

```json
{
  "virtual_vehicle_id": "VV-1234567890",
  "vehicle_type": "VAN",
  "capacity_kg": 1000,
  "used_weight_kg": 620,
  "remaining_weight_kg": 380,
  "parcel_ids": ["P001", "P002"]
}
```

The colleague's fleet optimizer can consume this output and assign a real
vehicle. That module is not implemented here.
