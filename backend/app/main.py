from fastapi import FastAPI
from app.core.config import settings
from app.db.database import Base, engine

# Import models before create_all
from app.models.parcel import Parcel
from app.models.virtual_vehicle import VirtualVehicle
from app.models.vehicle_capability import VehicleCapability

from app.api.v1 import (
    auth, vehicles, maintenance, predictions, demand, deliveries,
    routes, trips, alerts, reports, parcels, optimization,
    virtual_vehicles, vehicle_capabilities, health
)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Shared Fleet Web App backend with HDBSCAN + NSGA-II parcel consolidation.",
)

for router in [
    health.router,
    auth.router, vehicles.router, maintenance.router, predictions.router,
    demand.router, deliveries.router, routes.router, trips.router,
    alerts.router, reports.router, parcels.router,
    optimization.router, virtual_vehicles.router, vehicle_capabilities.router
]:
    app.include_router(router, prefix="/api/v1")

@app.get("/")
def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "research_pipeline": [
            "parcel ingestion",
            "preprocessing",
            "HDBSCAN clustering",
            "NSGA-II vehicle-type/load optimization",
            "virtual vehicle generation",
            "dynamic parcel insertion",
        ],
        "fleet_assignment": "not included",
    }
