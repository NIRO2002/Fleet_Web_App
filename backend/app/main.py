import asyncio
import socket
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings
from app.db.database import init_database
from app.workers.optimization_worker import run_forever

from app.api.v1 import (
    auth, vehicles, maintenance, predictions, demand, deliveries,
    routes, trips, alerts, reports, parcels, optimization,
    virtual_vehicles, vehicle_types, vocabularies, depots, plans, health
)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    client = await init_database()
    worker_task = None
    if settings.run_optimization_worker_inprocess:
        worker_id = f"api-{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        worker_task = asyncio.create_task(run_forever(worker_id))
    yield
    if worker_task is not None:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    client.close()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Shared Fleet Web App backend with HDBSCAN + NSGA-II parcel consolidation.",
    lifespan=lifespan,
)

for router in [
    health.router,
    auth.router, vehicles.router, maintenance.router, predictions.router,
    demand.router, deliveries.router, routes.router, trips.router,
    alerts.router, reports.router, parcels.router,
    optimization.router, virtual_vehicles.router,
    vehicle_types.router,
    vocabularies.router, depots.router, plans.router,
]:
    app.include_router(router, prefix="/api/v1")

@app.get("/")
async def root():
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
