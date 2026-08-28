"""Single-process MongoDB optimization worker.

Run from ``backend`` with: ``python -m app.workers.optimization_worker``.
"""
import asyncio
import socket
import uuid
from datetime import timedelta

from app.core.config import settings
from app.db.database import init_database
from app.services.optimization_job_service import (
    claim_next_job, execute_claimed_job, recover_stale_jobs, update_job,
)
from app.utils_datetime import utcnow


async def _heartbeat(job_id: str, worker_id: str):
    interval = max(5, settings.optimization_job_lease_seconds // 3)
    while True:
        await asyncio.sleep(interval)
        now = utcnow()
        await update_job(
            job_id, worker_id=worker_id, heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=settings.optimization_job_lease_seconds),
            stage="NSGA-II", progress_percent=20,
            message="NSGA-II optimization is running",
        )


async def run_once(worker_id: str):
    await recover_stale_jobs()
    job = await claim_next_job(worker_id, settings.optimization_job_lease_seconds)
    if job is None:
        return False
    heartbeat = asyncio.create_task(_heartbeat(job.job_id, worker_id))
    try:
        await execute_claimed_job(job)
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass
    return True


async def run_forever(worker_id: str):
    """Claim/execute jobs until cancelled. Never raises: a bad iteration is
    logged and retried after the poll interval instead of killing the loop
    and silently leaving the queue unprocessed."""
    while True:
        try:
            worked = await run_once(worker_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            worked = False
        if not worked:
            await asyncio.sleep(settings.optimization_worker_poll_seconds)


async def main():
    client = await init_database()
    worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    try:
        await run_forever(worker_id)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
