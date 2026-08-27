"""Persistent optimization queue, reservation, and worker execution services."""
import hashlib
import uuid
from datetime import timedelta

from fastapi import HTTPException
from pymongo import ReturnDocument, UpdateOne

from app.models.load_plan import LoadPlan
from app.models.optimization_job import OptimizationJob
from app.models.parcel import Parcel
from app.optimization.assignment_problem import AssignmentConfig
from app.schemas.optimization import OptimizationRequest
from app.services.depot_service import get_depot_or_fail
from app.services.optimization_service import optimize_load
from app.utils_datetime import utcnow

ACTIVE = ("QUEUED", "RUNNING")
ELIGIBLE = ("PENDING", "FAILED")


def _scope_key(payload: OptimizationRequest) -> str:
    if payload.cluster_id is not None:
        return f"cluster:{payload.depot_id}:{payload.delivery_date}:{payload.cluster_id}"
    ids = sorted(set(payload.parcel_ids or []))
    digest = hashlib.sha256("\0".join(ids).encode()).hexdigest()
    return f"parcels:{digest}"


async def resolve_optimization_request(payload: OptimizationRequest, *, require_unreserved=True,
                                       depot_resolver=None, report_cluster_conflicts=True):
    depot_resolver = depot_resolver or get_depot_or_fail
    if payload.cluster_id == -1:
        raise HTTPException(400, "cluster_id -1 (noise) is not a valid optimization target")
    if payload.parcel_ids:
        requested = list(dict.fromkeys(payload.parcel_ids))
        parcels = await Parcel.find({"parcel_id": {"$in": requested}}).to_list()
        found = {p.parcel_id for p in parcels}
        missing = [pid for pid in requested if pid not in found]
        if missing:
            raise HTTPException(404, f"Parcel IDs not found: {', '.join(missing)}")
        conflicts = [p for p in parcels if p.plan_id is not None or p.status not in ELIGIBLE or
                     (require_unreserved and getattr(p, "optimization_job_id", None) is not None)]
        if conflicts:
            detail = "; ".join(
                f"{p.parcel_id} (plan_id={p.plan_id}, reservation={getattr(p, 'optimization_job_id', None)})" for p in conflicts
            )
            raise HTTPException(409, f"Already planned or reserved: {detail}")
    elif payload.cluster_id is not None:
        query = {
            "cluster_id": payload.cluster_id, "depot_id": payload.depot_id,
            "delivery_date": payload.delivery_date, "status": {"$in": list(ELIGIBLE)},
        }
        if require_unreserved:
            query["optimization_job_id"] = None
        parcels = await Parcel.find(query).to_list()
        if not parcels:
            broader = await Parcel.find({
                "cluster_id": payload.cluster_id, "depot_id": payload.depot_id,
                "delivery_date": payload.delivery_date,
            }).to_list()
            active = [getattr(p, "optimization_job_id", None) for p in broader if getattr(p, "optimization_job_id", None)]
            if active and report_cluster_conflicts:
                raise HTTPException(409, f"Optimization already queued/running: {active[0]}")
            planned = sorted({p.plan_id for p in broader if p.plan_id})
            if planned and report_cluster_conflicts:
                raise HTTPException(409, f"Already planned: {', '.join(planned)}")
            raise HTTPException(404, "No matching parcels")
    else:
        raise HTTPException(400, "Provide cluster_id or parcel_ids")

    depot_ids = {p.depot_id for p in parcels}
    dates = {p.delivery_date for p in parcels}
    if len(depot_ids) != 1 or None in depot_ids:
        raise HTTPException(400, "Selected parcels must share exactly one depot_id")
    if len(dates) != 1:
        raise HTTPException(400, "Selected parcels must share exactly one delivery_date")
    resolved_depot_id = next(iter(depot_ids))
    depot = await depot_resolver(resolved_depot_id)
    if (payload.depot_latitude is None) != (payload.depot_longitude is None):
        raise HTTPException(400, "depot_latitude and depot_longitude overrides must be supplied together")
    if payload.depot_latitude is not None and payload.depot_id != resolved_depot_id:
        raise HTTPException(400, "depot coordinate override requires a matching depot_id")
    return parcels, depot, resolved_depot_id, next(iter(dates))


async def create_optimization_job(payload: OptimizationRequest, *, batch_id=None):
    scope_key = _scope_key(payload)
    existing = await OptimizationJob.find({"scope_key": scope_key, "status": {"$in": list(ACTIVE)}}).first_or_none()
    if existing:
        return existing, False
    parcels, depot, depot_id, delivery_date = await resolve_optimization_request(payload)
    job_id = f"JOB-{uuid.uuid4().hex[:12].upper()}"
    job = OptimizationJob(
        job_id=job_id, status="QUEUED", job_type="SINGLE_CLUSTER" if payload.cluster_id is not None else "PARCEL_SET",
        scope_key=scope_key, batch_id=batch_id, cluster_id=payload.cluster_id,
        depot_id=depot_id, delivery_date=delivery_date,
        parcel_ids=sorted(p.parcel_id for p in parcels),
        depot_latitude=payload.depot_latitude if payload.depot_latitude is not None else depot.lat,
        depot_longitude=payload.depot_longitude if payload.depot_longitude is not None else depot.lng,
    )
    await job.insert()
    collection = Parcel.get_motor_collection()
    result = await collection.update_many(
        {"parcel_id": {"$in": job.parcel_ids}, "status": {"$in": list(ELIGIBLE)},
         "plan_id": None, "optimization_job_id": None},
        {"$set": {"optimization_job_id": job_id}},
    )
    if result.modified_count != len(job.parcel_ids):
        await collection.update_many(
            {"optimization_job_id": job_id}, {"$set": {"optimization_job_id": None}}
        )
        await job.delete()
        raise HTTPException(409, "One or more parcels were reserved concurrently; no reservation was retained")
    return job, True


async def claim_next_job(worker_id: str, lease_seconds: int):
    now = utcnow(); lease = now + timedelta(seconds=lease_seconds)
    raw = await OptimizationJob.get_motor_collection().find_one_and_update(
        {"status": "QUEUED"},
        {"$set": {"status": "RUNNING", "worker_id": worker_id, "started_at": now,
                  "heartbeat_at": now, "lease_expires_at": lease, "progress_percent": 5,
                  "stage": "LOADING", "message": "Loading reserved parcels", "updated_at": now}},
        sort=[("created_at", 1)], return_document=ReturnDocument.AFTER,
    )
    return OptimizationJob.model_validate(raw) if raw else None


async def update_job(job_id: str, **fields):
    fields["updated_at"] = utcnow()
    await OptimizationJob.get_motor_collection().update_one({"job_id": job_id}, {"$set": fields})


async def execute_claimed_job(job: OptimizationJob):
    try:
        parcels = await Parcel.find({"parcel_id": {"$in": job.parcel_ids}, "optimization_job_id": job.job_id}).to_list()
        if len(parcels) != len(job.parcel_ids):
            raise RuntimeError("Reserved parcel set is incomplete")
        depot = await get_depot_or_fail(job.depot_id)
        await update_job(job.job_id, progress_percent=15, stage="PREPARING", message="Preparing NSGA-II optimization")
        result, vehicles = await optimize_load(
            parcels, depot_id=job.depot_id, depot_lat=job.depot_latitude,
            depot_lon=job.depot_longitude, delivery_date=job.delivery_date, seed=job.seed,
            config=AssignmentConfig(depot_lat=job.depot_latitude, depot_lon=job.depot_longitude,
                                    max_vehicle_slots=depot.vehicle_capacity),
            depot_operating_end=depot.operating_hours_end,
            depot_vehicle_capacity=depot.vehicle_capacity,
        )
        await update_job(job.job_id, progress_percent=95, stage="VALIDATING", message="Validating persisted load plan")
        plan = await LoadPlan.find_one(LoadPlan.plan_id == result["plan_id"])
        if plan is None or plan.n_parcels != len(job.parcel_ids) or len(vehicles) != plan.n_vehicles:
            raise RuntimeError("Persisted optimization result failed validation")
        await update_job(
            job.job_id, status="COMPLETED", progress_percent=100, stage="COMPLETED",
            message="Optimization completed", plan_id=result["plan_id"],
            virtual_vehicle_ids=result.get("virtual_vehicle_ids", []),
            result_summary={"n_parcels": len(job.parcel_ids), "n_vehicles": len(vehicles),
                            "cluster_id": job.cluster_id},
            completed_at=utcnow(), heartbeat_at=None, lease_expires_at=None,
        )
        return result
    except Exception as exc:
        # optimize_load clears reservations atomically with PLANNED. Only
        # still-owned reservations are released here; planned parcels are
        # never made eligible again after a late persistence failure.
        await Parcel.get_motor_collection().update_many(
            {"optimization_job_id": job.job_id}, {"$set": {"optimization_job_id": None}}
        )
        current = await Parcel.find({"parcel_id": {"$in": job.parcel_ids}}).to_list()
        partial_plan_ids = sorted({p.plan_id for p in current if p.plan_id})
        await update_job(
            job.job_id, status="FAILED", stage="FAILED", message="Optimization failed",
            error_code="PARTIAL_PERSISTENCE" if partial_plan_ids else type(exc).__name__,
            error_message=str(exc)[:500],
            result_summary={"partial_plan_ids": partial_plan_ids} if partial_plan_ids else None,
            completed_at=utcnow(), heartbeat_at=None, lease_expires_at=None,
        )
        return None


async def recover_stale_jobs():
    now = utcnow()
    stale = await OptimizationJob.find({"status": "RUNNING", "lease_expires_at": {"$lt": now}}).to_list()
    for job in stale:
        await Parcel.get_motor_collection().update_many(
            {"optimization_job_id": job.job_id}, {"$set": {"optimization_job_id": None}}
        )
        current = await Parcel.find({"parcel_id": {"$in": job.parcel_ids}}).to_list()
        partial_plan_ids = sorted({p.plan_id for p in current if p.plan_id})
        await update_job(job.job_id, status="FAILED", stage="FAILED", progress_percent=job.progress_percent,
                         message="Worker lease expired", error_code="WORKER_LOST",
                         error_message="Optimization worker stopped before completion",
                         result_summary={"partial_plan_ids": partial_plan_ids} if partial_plan_ids else None,
                         completed_at=now, heartbeat_at=None, lease_expires_at=None)
    return len(stale)
