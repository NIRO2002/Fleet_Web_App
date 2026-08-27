from datetime import date as date_type
import uuid

from fastapi import APIRouter, HTTPException, Response

from app.core.config import settings
from app.models.load_plan import LoadPlan
from app.models.parcel import Parcel
from app.schemas.optimization import OptimizationBatchRequest, OptimizationRequest
from app.services.optimization_service import optimize_load
from app.services.depot_service import get_depot_or_fail
from app.optimization.assignment_problem import AssignmentConfig
from app.services.export_service import load_plan_csv, load_plan_payload
from app.models.optimization_job import OptimizationJob
from app.services.optimization_job_service import create_optimization_job, resolve_optimization_request

router = APIRouter(prefix="/optimization", tags=["optimization"])


@router.get("/plans")
async def find_plan(depot_id: str, delivery_date: date_type):
    """Most recent plan for a (depot_id, delivery_date), if one exists --
    lets a caller avoid re-running an optimization that already ran."""
    plan = await LoadPlan.find(
        LoadPlan.depot_id == depot_id, LoadPlan.delivery_date == delivery_date,
    ).sort("-created_at").first_or_none()
    if plan is None:
        return None
    return await load_plan_payload(plan.plan_id)


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str):
    return await load_plan_payload(plan_id)


@router.get("/plans/{plan_id}/export.csv")
async def export_plan_csv(plan_id: str):
    return Response(
        await load_plan_csv(plan_id),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{plan_id}.csv"'},
    )

@router.post("/run")
async def run(payload: OptimizationRequest):
    try:
        parcels, depot, resolved_depot_id, resolved_date = await resolve_optimization_request(
            payload, require_unreserved=True, depot_resolver=get_depot_or_fail,
            report_cluster_conflicts=False,
        )
        # optimize_load sets status=PLANNED/plan_id on every parcel it
        # covers (app/services/optimization_service.py). An explicit
        # parcel_ids request can name a parcel a prior run already claimed
        # -- unlike the cluster_id branch's PENDING filter below, there's no
        # query-level way to silently skip just one id out of a caller-given
        # list, so this must fail loudly rather than silently re-plan it.
        depot_lat = payload.depot_latitude if payload.depot_latitude is not None else depot.lat
        depot_lon = payload.depot_longitude if payload.depot_longitude is not None else depot.lng
        result, _ = await optimize_load(
            parcels,
            depot_id=resolved_depot_id,
            depot_lat=depot_lat,
            depot_lon=depot_lon,
            delivery_date=resolved_date,
            config=AssignmentConfig(
                depot_lat=depot_lat,
                depot_lon=depot_lon,
                max_vehicle_slots=depot.vehicle_capacity,
            ),
            depot_operating_end=depot.operating_hours_end,
            depot_vehicle_capacity=depot.vehicle_capacity,
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _job_payload(job: OptimizationJob):
    return job.model_dump(mode="json", exclude={"id", "revision_id", "scope_key", "worker_id", "lease_expires_at"})


@router.post("/jobs", status_code=202)
async def create_job(payload: OptimizationRequest):
    job, created = await create_optimization_job(payload)
    response = _job_payload(job)
    response["created"] = created
    return response


@router.post("/jobs/batch", status_code=202)
async def create_job_batch(payload: OptimizationBatchRequest):
    batch_id = f"BATCH-{uuid.uuid4().hex[:12].upper()}"
    jobs = []
    newly_created = []
    try:
        for cluster_id in payload.cluster_ids:
            job, created = await create_optimization_job(OptimizationRequest(
                cluster_id=cluster_id, depot_id=payload.depot_id, delivery_date=payload.delivery_date,
                depot_latitude=payload.depot_latitude, depot_longitude=payload.depot_longitude,
            ), batch_id=batch_id)
            jobs.append(job)
            if created:
                newly_created.append(job)
    except Exception:
        for job in newly_created:
            await Parcel.get_motor_collection().update_many(
                {"optimization_job_id": job.job_id}, {"$set": {"optimization_job_id": None}}
            )
            await job.delete()
        raise
    return {"batch_id": batch_id, "jobs": [_job_payload(job) for job in jobs]}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = await OptimizationJob.find_one(OptimizationJob.job_id == job_id)
    if job is None:
        raise HTTPException(404, "Optimization job not found")
    return _job_payload(job)


@router.get("/jobs")
async def list_jobs(status: str | None = None, depot_id: str | None = None,
                    delivery_date: date_type | None = None, batch_id: str | None = None,
                    limit: int = 50):
    query = {}
    if status: query["status"] = status
    if depot_id: query["depot_id"] = depot_id
    if delivery_date: query["delivery_date"] = delivery_date
    if batch_id: query["batch_id"] = batch_id
    rows = await OptimizationJob.find(query).sort("-created_at").limit(min(max(limit, 1), 200)).to_list()
    return [_job_payload(job) for job in rows]
