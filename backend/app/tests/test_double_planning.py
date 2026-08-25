"""optimize_load sets status=PLANNED and plan_id on every parcel it covers
(app/services/optimization_service.py), but /optimization/run used to
resolve parcels with no status filter -- a second run against the same
cluster_id or parcel_ids would silently create a second LoadPlan over
already-planned parcels. See app/api/v1/optimization.py.
"""
import asyncio
from dataclasses import dataclass
from datetime import date

import pytest
from fastapi import HTTPException

from app.api.v1 import optimization as optimization_api
from app.schemas.optimization import OptimizationRequest


@dataclass
class FakeParcel:
    parcel_id: str
    depot_id: str
    delivery_date: date
    cluster_id: int
    status: str = "PENDING"
    plan_id: str | None = None


class FakeDepot:
    def __init__(self, depot_id):
        self.depot_id = depot_id
        self.lat = 6.9271
        self.lng = 79.8612
        self.operating_hours_end = "20:00"
        self.vehicle_capacity = 50


class FakeQuery:
    def __init__(self, matches):
        self._matches = matches

    async def to_list(self):
        return self._matches


def _install_fake_parcels(monkeypatch, parcels):
    def fake_find(query):
        if "parcel_id" in query and isinstance(query["parcel_id"], dict):
            ids = set(query["parcel_id"]["$in"])
            matches = [p for p in parcels if p.parcel_id in ids]
        else:
            matches = [p for p in parcels if all(
                getattr(p, key) in value["$in"] if isinstance(value, dict) and "$in" in value
                else getattr(p, key) == value
                for key, value in query.items()
            )]
        return FakeQuery(matches)

    monkeypatch.setattr(optimization_api.Parcel, "find", staticmethod(fake_find))


def _install_fake_optimize(monkeypatch, run_count):
    async def fake_get_depot_or_fail(depot_id):
        return FakeDepot(depot_id)

    async def fake_optimize_load(parcels, **kwargs):
        run_count["n"] += 1
        plan_id = f"PLAN-{run_count['n']}"
        # Mirrors the real optimize_load's side effect (Fix Pass 2 item C):
        # every parcel it covers is claimed by the resulting plan.
        for p in parcels:
            p.status = "PLANNED"
            p.plan_id = plan_id
        return {"plan_id": plan_id, "parcel_ids": sorted(p.parcel_id for p in parcels)}, None

    monkeypatch.setattr(optimization_api, "get_depot_or_fail", fake_get_depot_or_fail)
    monkeypatch.setattr(optimization_api, "optimize_load", fake_optimize_load)


def test_second_run_on_same_cluster_does_not_create_second_plan(monkeypatch):
    depot_id, delivery_date = "D-CMB-001", date(2026, 1, 5)
    parcels = [
        FakeParcel("A-1", depot_id, delivery_date, cluster_id=0),
        FakeParcel("A-2", depot_id, delivery_date, cluster_id=0),
    ]
    _install_fake_parcels(monkeypatch, parcels)
    run_count = {"n": 0}
    _install_fake_optimize(monkeypatch, run_count)

    payload = OptimizationRequest(cluster_id=0, depot_id=depot_id, delivery_date=delivery_date)

    first = asyncio.run(optimization_api.run(payload))
    assert first["plan_id"] == "PLAN-1"
    assert run_count["n"] == 1
    assert all(p.status == "PLANNED" and p.plan_id == "PLAN-1" for p in parcels)

    # Second call: both parcels are now PLANNED, so the eligible query finds
    # nothing left in this cluster -- not a second LoadPlan.
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(optimization_api.run(payload))
    assert exc_info.value.status_code == 404
    assert run_count["n"] == 1  # optimize_load must not have run again
def test_parcel_ids_already_planned_is_rejected_with_409(monkeypatch):
    parcels = [
        FakeParcel("X-1", "D-CMB-001", date(2026, 1, 5), cluster_id=2, status="PLANNED", plan_id="PLAN-OLD"),
    ]
    _install_fake_parcels(monkeypatch, parcels)
    run_count = {"n": 0}
    _install_fake_optimize(monkeypatch, run_count)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(optimization_api.run(OptimizationRequest(parcel_ids=["X-1"])))

    assert exc_info.value.status_code == 409
    assert "PLAN-OLD" in exc_info.value.detail
    assert run_count["n"] == 0  # optimize_load must never have been called
