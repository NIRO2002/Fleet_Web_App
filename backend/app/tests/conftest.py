import asyncio
import uuid
import pytest
import mongomock.database
import mongomock.collection
from beanie import init_beanie
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.db.database import DOCUMENT_MODELS
from app.evaluation.real_data import real_instance_payloads
from app.evaluation.synthetic_data import generate_synthetic_parcels
from app.schemas.parcel import ParcelIn
from app.services.data_service import upsert_parcel

class MongoTestContext:
    def __init__(self):
        self.pending = []
    def run(self, awaitable):
        return asyncio.run(awaitable)
    def add(self, obj):
        self.pending.append(obj)
    def add_all(self, objects):
        self.pending.extend(objects)
    def commit(self):
        async def _commit():
            for obj in self.pending:
                await obj.save()
            self.pending.clear()
        return self.run(_commit())
    def refresh(self, obj):
        return obj
    def query(self, model, *extra):
        return MongoQuery(self, model)

class MongoQuery:
    def __init__(self, context, model):
        self.context, self.model, self.conditions = context, model, []
    def filter(self, *conditions):
        self.conditions.extend(conditions)
        return self
    def filter_by(self, **values):
        self.conditions.append(values)
        return self
    def order_by(self, *args):
        return self
    def first(self):
        return self.context.run(self.model.find(*self.conditions).first_or_none())
    def all(self):
        from app.models.parcel_assignment import ParcelAssignment
        from app.models.load_plan import LoadPlan
        if self.model is ParcelAssignment:
            plans = self.context.run(LoadPlan.find_all().to_list())
            rows = [a for plan in plans for vehicle in plan.vehicles for a in vehicle.assignments]
            for condition in self.conditions:
                if isinstance(condition, dict):
                    rows = [row for row in rows if all(getattr(row, key) == value for key, value in condition.items())]
            return rows
        return self.context.run(self.model.find(*self.conditions).to_list())
    def count(self):
        return self.context.run(self.model.find(*self.conditions).count())

_list_collection_names = mongomock.database.Database.list_collection_names
def _compatible_list_collection_names(self, *args, **kwargs):
    kwargs.pop("authorizedCollections", None)
    kwargs.pop("nameOnly", None)
    return _list_collection_names(self, *args, **kwargs)
mongomock.database.Database.list_collection_names = _compatible_list_collection_names

_bulk_add_update = mongomock.collection.BulkOperationBuilder.add_update
def _compatible_bulk_add_update(self, *args, **kwargs):
    kwargs.pop("sort", None)
    return _bulk_add_update(self, *args, **kwargs)
mongomock.collection.BulkOperationBuilder.add_update = _compatible_bulk_add_update

@pytest.fixture(autouse=True)
def mongo_database():
    client = AsyncMongoMockClient()
    asyncio.run(init_beanie(database=client[f"test_{uuid.uuid4().hex}"], document_models=DOCUMENT_MODELS))
    yield client
    client.close()

@pytest.fixture()
def db_engine(mongo_database):
    return mongo_database

@pytest.fixture()
def db_session():
    return MongoTestContext()

@pytest.fixture()
def client():
    from app.main import app
    test_client = TestClient(app)
    yield test_client
    test_client.close()

DEFAULT_DEPOT_ID = "DEPOT-1"
DEFAULT_DELIVERY_DATE = "2026-08-20"

@pytest.fixture()
def parcel_factory():
    def _factory(n=20, seed=0, n_clusters=2, depot_lat=6.9271, depot_lon=79.8612,
                 depot_id=DEFAULT_DEPOT_ID, delivery_date=DEFAULT_DELIVERY_DATE):
        return generate_synthetic_parcels(n=n, seed=seed, n_clusters=n_clusters,
            depot_lat=depot_lat, depot_lon=depot_lon, depot_id=depot_id, delivery_date=delivery_date)
    return _factory

@pytest.fixture()
def real_instance(db_session):
    def _load(depot_id="D-CMB-001", delivery_date="2026-01-05"):
        return [db_session.run(upsert_parcel(ParcelIn(**p))) for p in real_instance_payloads(depot_id, delivery_date)]
    return _load
