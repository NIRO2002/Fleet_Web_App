import asyncio
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from beanie import init_beanie
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.models.load_plan import LoadPlan
from app.models.optimization_job import OptimizationJob
from app.models.parcel import Parcel
from app.schemas.optimization import OptimizationRequest
from app.services import optimization_job_service as jobs
from app.utils_datetime import utcnow


TARGET = date(2026, 1, 5)


def parcel(parcel_id, cluster_id=4):
    return Parcel(
        parcel_id=parcel_id, depot_id="D-CMB-001", delivery_date=TARGET,
        cluster_id=cluster_id, latitude=6.9271, longitude=79.8612,
        weight_kg=2, volume_m3=.01, time_window_start="08:00", time_window_end="12:00",
    )


async def setup_db(name, row_factory):
    client = AsyncMongoMockClient()
    await init_beanie(database=client[name], document_models=[Parcel, OptimizationJob, LoadPlan])
    await Parcel.insert_many(row_factory())
    return client


def depot(_depot_id):
    return SimpleNamespace(lat=6.9271, lng=79.8612, vehicle_capacity=50, operating_hours_end="20:00")


def test_create_duplicate_overlap_and_atomic_claim(monkeypatch):
    async def scenario():
        client = await setup_db("jobs_reservation", lambda: [parcel("P1"), parcel("P2"), parcel("P3", 5)])
        async def fake_depot(depot_id): return depot(depot_id)
        monkeypatch.setattr(jobs, "get_depot_or_fail", fake_depot)

        payload = OptimizationRequest(cluster_id=4, depot_id="D-CMB-001", delivery_date=TARGET)
        first, created = await jobs.create_optimization_job(payload)
        duplicate, duplicate_created = await jobs.create_optimization_job(payload)
        assert created is True and duplicate_created is False and duplicate.job_id == first.job_id
        assert await Parcel.find({"optimization_job_id": first.job_id}).count() == 2

        with pytest.raises(HTTPException) as conflict:
            await jobs.create_optimization_job(OptimizationRequest(parcel_ids=["P2", "P3"]))
        assert conflict.value.status_code == 409
        assert (await Parcel.find_one(Parcel.parcel_id == "P3")).optimization_job_id is None

        claims = await asyncio.gather(jobs.claim_next_job("W1", 120), jobs.claim_next_job("W2", 120))
        assert sum(claim is not None for claim in claims) == 1
        assert next(claim for claim in claims if claim).status == "RUNNING"
        client.close()
    asyncio.run(scenario())


def test_worker_completion_and_failure_release(monkeypatch):
    async def scenario():
        client = await setup_db("jobs_lifecycle", lambda: [parcel("OK", 1), parcel("FAIL", 2)])
        async def fake_depot(depot_id): return depot(depot_id)
        monkeypatch.setattr(jobs, "get_depot_or_fail", fake_depot)

        ok, _ = await jobs.create_optimization_job(OptimizationRequest(
            cluster_id=1, depot_id="D-CMB-001", delivery_date=TARGET,
        ))
        claimed = await jobs.claim_next_job("WORKER", 120)
        async def fake_optimize(parcels, **_kwargs):
            await Parcel.get_motor_collection().update_many(
                {"optimization_job_id": ok.job_id},
                {"$set": {"optimization_job_id": None, "status": "PLANNED", "plan_id": "PLAN-OK"}},
            )
            return {"plan_id": "PLAN-OK", "virtual_vehicle_ids": ["VV-1"]}, [object()]
        monkeypatch.setattr(jobs, "optimize_load", fake_optimize)
        monkeypatch.setattr(jobs.LoadPlan, "find_one", staticmethod(lambda *_args, **_kwargs: _Awaitable(SimpleNamespace(n_parcels=1, n_vehicles=1))))
        await jobs.execute_claimed_job(claimed)
        completed = await OptimizationJob.find_one(OptimizationJob.job_id == ok.job_id)
        assert completed.status == "COMPLETED" and completed.progress_percent == 100
        assert completed.plan_id == "PLAN-OK" and completed.virtual_vehicle_ids == ["VV-1"]

        failed_job, _ = await jobs.create_optimization_job(OptimizationRequest(
            cluster_id=2, depot_id="D-CMB-001", delivery_date=TARGET,
        ))
        failed_claim = await jobs.claim_next_job("WORKER", 120)
        async def fail(*_args, **_kwargs): raise RuntimeError("safe optimizer failure")
        monkeypatch.setattr(jobs, "optimize_load", fail)
        await jobs.execute_claimed_job(failed_claim)
        failed = await OptimizationJob.find_one(OptimizationJob.job_id == failed_job.job_id)
        assert failed.status == "FAILED" and failed.error_message == "safe optimizer failure"
        assert (await Parcel.find_one(Parcel.parcel_id == "FAIL")).optimization_job_id is None
        client.close()
    asyncio.run(scenario())


class _Awaitable:
    def __init__(self, value): self.value = value
    def __await__(self):
        async def get(): return self.value
        return get().__await__()


def test_cancel_queued_job_is_immediate_and_releases_parcels(monkeypatch):
    async def scenario():
        client = await setup_db("jobs_cancel_queued", lambda: [parcel("Q1", 9)])
        async def fake_depot(depot_id): return depot(depot_id)
        monkeypatch.setattr(jobs, "get_depot_or_fail", fake_depot)
        job, _ = await jobs.create_optimization_job(OptimizationRequest(
            cluster_id=9, depot_id="D-CMB-001", delivery_date=TARGET,
        ))
        cancelled = await jobs.cancel_job(job.job_id)
        assert cancelled.status == "CANCELLED"
        assert (await Parcel.find_one(Parcel.parcel_id == "Q1")).optimization_job_id is None
        with pytest.raises(HTTPException) as already_terminal:
            await jobs.cancel_job(job.job_id)
        assert already_terminal.value.status_code == 409
        client.close()
    asyncio.run(scenario())


def test_cancel_running_job_flags_then_finalizes_as_cancelled(monkeypatch):
    from app.optimization.assignment_problem import OptimizationCancelled

    async def scenario():
        client = await setup_db("jobs_cancel_running", lambda: [parcel("R1", 10)])
        async def fake_depot(depot_id): return depot(depot_id)
        monkeypatch.setattr(jobs, "get_depot_or_fail", fake_depot)
        job, _ = await jobs.create_optimization_job(OptimizationRequest(
            cluster_id=10, depot_id="D-CMB-001", delivery_date=TARGET,
        ))
        claimed = await jobs.claim_next_job("WORKER", 120)

        flagged = await jobs.cancel_job(job.job_id)
        assert flagged.status == "RUNNING" and flagged.cancel_requested is True

        # Simulates assignment_problem._CancelCallback observing the flag
        # mid-run and aborting the NSGA-II loop before anything persists.
        async def cancelled_mid_run(*_args, **_kwargs):
            raise OptimizationCancelled("stopped by test")
        monkeypatch.setattr(jobs, "optimize_load", cancelled_mid_run)

        await jobs.execute_claimed_job(claimed)
        final = await OptimizationJob.find_one(OptimizationJob.job_id == job.job_id)
        assert final.status == "CANCELLED"
        assert (await Parcel.find_one(Parcel.parcel_id == "R1")).optimization_job_id is None
        client.close()
    asyncio.run(scenario())


def test_delete_job_requires_terminal_status(monkeypatch):
    async def scenario():
        client = await setup_db("jobs_delete", lambda: [parcel("D1", 11)])
        async def fake_depot(depot_id): return depot(depot_id)
        monkeypatch.setattr(jobs, "get_depot_or_fail", fake_depot)
        job, _ = await jobs.create_optimization_job(OptimizationRequest(
            cluster_id=11, depot_id="D-CMB-001", delivery_date=TARGET,
        ))
        with pytest.raises(HTTPException) as active:
            await jobs.delete_job(job.job_id)
        assert active.value.status_code == 409

        await jobs.cancel_job(job.job_id)
        await jobs.delete_job(job.job_id)
        assert await OptimizationJob.find_one(OptimizationJob.job_id == job.job_id) is None
        client.close()
    asyncio.run(scenario())


def test_stale_running_job_fails_without_automatic_retry(monkeypatch):
    async def scenario():
        client = await setup_db("jobs_stale", lambda: [parcel("STALE", 8)])
        async def fake_depot(depot_id): return depot(depot_id)
        monkeypatch.setattr(jobs, "get_depot_or_fail", fake_depot)
        job, _ = await jobs.create_optimization_job(OptimizationRequest(
            cluster_id=8, depot_id="D-CMB-001", delivery_date=TARGET,
        ))
        await jobs.update_job(job.job_id, status="RUNNING", lease_expires_at=utcnow()-timedelta(seconds=1))
        assert await jobs.recover_stale_jobs() == 1
        recovered = await OptimizationJob.find_one(OptimizationJob.job_id == job.job_id)
        assert recovered.status == "FAILED" and recovered.error_code == "WORKER_LOST"
        assert (await Parcel.find_one(Parcel.parcel_id == "STALE")).optimization_job_id is None
        assert await jobs.claim_next_job("OTHER", 120) is None
        client.close()
    asyncio.run(scenario())
