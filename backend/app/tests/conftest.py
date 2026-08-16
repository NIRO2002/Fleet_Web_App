"""Phase 0 (Backend Remediation) shared test fixtures.

Provides an isolated in-memory SQLite session per test, a TestClient wired to
that session via dependency override, and a deterministic synthetic parcel
factory so tests never depend on the developer's local `fleet_web_app.db`.
"""
import random

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.session import get_db


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    testing_session_local = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    from app.main import app

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


DEFAULT_DEPOT_ID = "DEPOT-1"
DEFAULT_DELIVERY_DATE = "2026-08-20"


def _parcel_payload(parcel_id, lat, lon, weight, volume, tw_start, tw_end, fragile, depot_id, delivery_date):
    return {
        "parcel_id": parcel_id,
        "depot_id": depot_id,
        "delivery_date": delivery_date,
        "latitude": lat,
        "longitude": lon,
        "weight_kg": weight,
        "volume_m3": volume,
        "time_window_start": tw_start,
        "time_window_end": tw_end,
        "fragile": fragile,
    }


@pytest.fixture()
def parcel_factory():
    """Deterministic synthetic parcel generator.

    Produces `n` parcels jittered tightly around `n_clusters` geographic
    centers near the depot, so HDBSCAN reliably finds distinct clusters at
    the default `min_cluster_size`. Same `seed` always yields the same set.
    """

    def _factory(
        n: int = 20,
        seed: int = 0,
        n_clusters: int = 2,
        depot_lat: float = 6.9271,
        depot_lon: float = 79.8612,
        depot_id: str = DEFAULT_DEPOT_ID,
        delivery_date: str = DEFAULT_DELIVERY_DATE,
    ) -> list[dict]:
        rng = random.Random(seed)
        centers = [
            (depot_lat + rng.uniform(-0.03, 0.03), depot_lon + rng.uniform(-0.03, 0.03))
            for _ in range(n_clusters)
        ]
        payloads = []
        for i in range(n):
            clat, clon = centers[i % n_clusters]
            lat = clat + rng.uniform(-0.002, 0.002)
            lon = clon + rng.uniform(-0.002, 0.002)
            weight = round(rng.uniform(1.0, 8.0), 2)
            volume = round(rng.uniform(0.01, 0.05), 3)
            start_h = rng.choice([9, 10, 11])
            end_h = start_h + 3
            payloads.append(
                _parcel_payload(
                    f"P{i:04d}",
                    lat,
                    lon,
                    weight,
                    volume,
                    f"{start_h:02d}:00",
                    f"{end_h:02d}:00",
                    rng.random() < 0.15,
                    depot_id,
                    delivery_date,
                )
            )
        return payloads

    return _factory
