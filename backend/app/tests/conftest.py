"""Phase 0 (Backend Remediation) shared test fixtures.

Provides an isolated in-memory SQLite session per test, a TestClient wired to
that session via dependency override, and a deterministic synthetic parcel
factory so tests never depend on the developer's local `fleet_web_app.db`.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.session import get_db
from app.evaluation.real_data import real_instance_payloads
from app.evaluation.synthetic_data import generate_synthetic_parcels
from app.schemas.parcel import ParcelIn
from app.services.data_service import upsert_parcel


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


@pytest.fixture()
def parcel_factory():
    """Deterministic synthetic parcel generator.

    Produces `n` parcels jittered tightly around `n_clusters` geographic
    centers near the depot, so HDBSCAN reliably finds distinct clusters at
    the default `min_cluster_size`. Same `seed` always yields the same set.

    Thin wrapper around `app.evaluation.synthetic_data.generate_synthetic_parcels`
    (Fix Pass 2 -- shared with the A.7 verification, the runtime harness, and
    the feasibility-invariant tests, instead of three near-identical
    generators)."""

    def _factory(
        n: int = 20,
        seed: int = 0,
        n_clusters: int = 2,
        depot_lat: float = 6.9271,
        depot_lon: float = 79.8612,
        depot_id: str = DEFAULT_DEPOT_ID,
        delivery_date: str = DEFAULT_DELIVERY_DATE,
    ) -> list[dict]:
        return generate_synthetic_parcels(
            n=n, seed=seed, n_clusters=n_clusters, depot_lat=depot_lat, depot_lon=depot_lon,
            depot_id=depot_id, delivery_date=delivery_date,
        )

    return _factory


@pytest.fixture()
def real_instance(db_session):
    """Fix Pass 4 item S5: loads one real (depot_id, delivery_date) instance
    from `data/parcels_sample_36000.csv` (via `app.evaluation.real_data`,
    which caches the CSV so this isn't a 36,000-row read per test) and
    persists it as real `Parcel` ORM rows in `db_session`, same as
    `parcel_factory` does for synthetic data. Defaults to the instance Fix
    Pass 4's S1 placement diagnosis was verified against."""

    def _load(depot_id: str = "D-CMB-001", delivery_date: str = "2026-01-05") -> list:
        payloads = real_instance_payloads(depot_id, delivery_date)
        return [upsert_parcel(db_session, ParcelIn(**p)) for p in payloads]

    return _load
