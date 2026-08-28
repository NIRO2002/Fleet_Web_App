from datetime import date, datetime

from beanie import Document, Indexed
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.db.bson import DATE_BSON_ENCODERS
from app.core.config import settings
from app.utils_datetime import utcnow


class OptimizationJob(Document):
    job_id: Indexed(str, unique=True)
    status: str = "QUEUED"
    job_type: str = "SINGLE_CLUSTER"
    scope_key: str = ""
    batch_id: str | None = None
    cluster_id: int | None = None
    depot_id: str
    delivery_date: date
    parcel_ids: list[str] = Field(default_factory=list)
    depot_latitude: float = settings.depot_latitude
    depot_longitude: float = settings.depot_longitude
    seed: int = 0
    progress_percent: int = 0
    stage: str = "QUEUED"
    message: str = "Waiting for optimization worker"
    plan_id: str | None = None
    virtual_vehicle_ids: list[str] = Field(default_factory=list)
    result_summary: dict | None = None
    error_code: str | None = None
    error_message: str | None = None
    worker_id: str | None = None
    heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None
    cancel_requested: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "optimization_jobs"
        bson_encoders = DATE_BSON_ENCODERS
        indexes = [
            IndexModel([("status", ASCENDING), ("created_at", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
            IndexModel([("batch_id", ASCENDING)]),
            IndexModel([("scope_key", ASCENDING), ("status", ASCENDING)]),
            IndexModel([("lease_expires_at", ASCENDING)]),
        ]
