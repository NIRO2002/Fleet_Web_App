"""HDBSCAN labels restart at 0 for every (depot_id, delivery_date) planning
instance (app/services/clustering_service.py), so the same cluster_id
legitimately exists across many unrelated instances. POST /optimization/run
must resolve cluster_id together with (depot_id, delivery_date), never on
cluster_id alone -- see app/api/v1/optimization.py and
docs/DESIGN_DECISIONS.md's "cluster_id is scoped, not globally unique" entry.
"""
import asyncio
from dataclasses import dataclass
from datetime import date

import pytest
from pydantic import ValidationError

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
    optimization_job_id: str | None = None


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


def _install_fake_optimize(monkeypatch, captured):
    async def fake_get_depot_or_fail(depot_id):
        return FakeDepot(depot_id)

    async def fake_optimize_load(parcels, **kwargs):
        captured["parcels"] = parcels
        captured["kwargs"] = kwargs
        return {"parcel_ids": sorted(p.parcel_id for p in parcels)}, None

    monkeypatch.setattr(optimization_api, "get_depot_or_fail", fake_get_depot_or_fail)
    monkeypatch.setattr(optimization_api, "optimize_load", fake_optimize_load)


def test_cluster_id_scoped_to_planning_instance(monkeypatch):
    """Two different (depot_id, delivery_date) instances both produce a
    cluster_id of 0. A request scoped to instance A must resolve only A's
    parcels -- this fails on the pre-fix global `{"cluster_id": N}` query,
    which would silently merge in instance B's parcels too and then trip
    the (now-unreachable-for-this-branch) single-depot/date assertion."""
    instance_a = [
        FakeParcel("A-1", "D-CMB-001", date(2026, 1, 5), 0),
        FakeParcel("A-2", "D-CMB-001", date(2026, 1, 5), 0),
    ]
    instance_b = [
        FakeParcel("B-1", "D-CMB-002", date(2026, 1, 6), 0),
        FakeParcel("B-2", "D-CMB-002", date(2026, 1, 6), 0),
    ]
    _install_fake_parcels(monkeypatch, instance_a + instance_b)
    captured = {}
    _install_fake_optimize(monkeypatch, captured)

    payload = OptimizationRequest(cluster_id=0, depot_id="D-CMB-001", delivery_date=date(2026, 1, 5))
    result = asyncio.run(optimization_api.run(payload))

    assert {p.parcel_id for p in captured["parcels"]} == {"A-1", "A-2"}
    assert result["parcel_ids"] == ["A-1", "A-2"]


def test_unscoped_cluster_id_request_is_rejected():
    """A legacy request supplying cluster_id without depot_id/delivery_date
    must fail schema validation -- FastAPI turns a pydantic ValidationError
    on the request body into an HTTP 422 automatically."""
    with pytest.raises(ValidationError, match="depot_id and delivery_date are required"):
        OptimizationRequest(cluster_id=0)


def test_parcel_ids_spanning_depots_returns_400_not_500(monkeypatch):
    """The parcel_ids branch is not scoped by the cluster_id branch's
    (depot_id, delivery_date, cluster_id) query, so a caller-supplied
    parcel_ids list spanning multiple depots is real, reachable bad input --
    it must be a clean HTTPException(400, ...), not an AssertionError
    (which would surface as an unhandled 500, and vanish entirely under
    `python -O`). See docs/DESIGN_DECISIONS.md."""
    from fastapi import HTTPException

    parcels = [
        FakeParcel("A-1", "D-CMB-001", date(2026, 1, 5), 0),
        FakeParcel("B-1", "D-CMB-002", date(2026, 1, 6), 0),
    ]
    _install_fake_parcels(monkeypatch, parcels)
    captured = {}
    _install_fake_optimize(monkeypatch, captured)

    payload = OptimizationRequest(parcel_ids=["A-1", "B-1"])
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(optimization_api.run(payload))

    assert exc_info.value.status_code == 400
    assert "depot_id" in exc_info.value.detail
    assert "parcels" not in captured


def test_mismatched_depot_override_is_rejected(monkeypatch):
    """A request claims depot_id=D-CMB-001, but the parcel_ids it actually
    supplies resolve to D-CMB-002's parcels, and it also supplies a
    depot_latitude/longitude override -- this must fail loudly instead of
    silently running the optimizer with an override lat/lon that doesn't
    correspond to the resolved parcels' real depot."""
    parcels = [
        FakeParcel("X-1", "D-CMB-002", date(2026, 1, 5), 3),
    ]
    _install_fake_parcels(monkeypatch, parcels)
    captured = {}
    _install_fake_optimize(monkeypatch, captured)

    payload = OptimizationRequest(
        parcel_ids=["X-1"],
        depot_id="D-CMB-001",  # claimed scope disagrees with X-1's real depot_id
        depot_latitude=6.85,
        depot_longitude=79.95,
    )
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(optimization_api.run(payload))
    assert exc_info.value.status_code == 400
    assert "depot_id" in exc_info.value.detail
    assert "parcels" not in captured  # optimize_load must never have been called


def test_override_without_depot_id_is_rejected(monkeypatch):
    """A depot_latitude/depot_longitude override with NO depot_id at all is
    unverifiable -- there's nothing to compare the override against -- and
    must be rejected just like an explicit mismatch, not silently passed
    through (the pre-fix gap: `payload.depot_id is not None` skipped this
    check entirely whenever depot_id was omitted)."""
    from fastapi import HTTPException

    parcels = [
        FakeParcel("X-1", "D-CMB-002", date(2026, 1, 5), 3),
    ]
    _install_fake_parcels(monkeypatch, parcels)
    captured = {}
    _install_fake_optimize(monkeypatch, captured)

    payload = OptimizationRequest(
        parcel_ids=["X-1"],
        # no depot_id supplied at all
        depot_latitude=6.85,
        depot_longitude=79.95,
    )
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(optimization_api.run(payload))
    assert exc_info.value.status_code == 400
    assert "depot_id" in exc_info.value.detail
    assert "parcels" not in captured
