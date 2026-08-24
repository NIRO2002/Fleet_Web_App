"""app/services/clustering_common.py's handle_noise leaves genuinely
unassignable points at cluster_id=-1 rather than silently dropping them
(see the module docstring on handle_noise). This must be visible, not
just quietly persisted: GET /parcels/clustering/unassigned must surface
them, and POST /parcels/clustering/train's response must count them --
but they must never be auto-optimized (app/api/v1/optimization.py rejects
cluster_id=-1 outright).
"""
import asyncio
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

from app.api.v1 import parcels as parcels_api


@dataclass
class FakeParcel:
    parcel_id: str
    depot_id: str
    delivery_date: date
    cluster_id: int
    status: str = "PENDING"


class FakeQuery:
    def __init__(self, matches):
        self._matches = matches

    async def to_list(self):
        return self._matches


def _install_fake_parcels(monkeypatch, parcels):
    def fake_find(query):
        matches = [p for p in parcels if all(getattr(p, key) == value for key, value in query.items())]
        return FakeQuery(matches)

    monkeypatch.setattr(parcels_api.Parcel, "find", staticmethod(fake_find))


def test_unassigned_endpoint_returns_noise_parcels(monkeypatch):
    depot_id, delivery_date = "D-CMB-001", date(2026, 1, 5)
    parcels = [
        FakeParcel("P-1", depot_id, delivery_date, cluster_id=2),
        FakeParcel("P-2", depot_id, delivery_date, cluster_id=-1),
        FakeParcel("P-3", depot_id, delivery_date, cluster_id=-1),
        # A different instance's noise must not leak in.
        FakeParcel("Q-1", "D-CMB-002", date(2026, 1, 6), cluster_id=-1),
        # A parcel already claimed by an earlier plan (not PENDING) that
        # happens to carry a stale cluster_id=-1 must not show up as if it
        # still needs attention.
        FakeParcel("P-4", depot_id, delivery_date, cluster_id=-1, status="PLANNED"),
    ]
    _install_fake_parcels(monkeypatch, parcels)

    result = asyncio.run(parcels_api.list_unassigned_parcels(depot_id=depot_id, delivery_date=delivery_date))

    assert {p.parcel_id for p in result} == {"P-2", "P-3"}


def test_train_response_counts_unassigned_parcels(monkeypatch):
    """cluster_id=-1 parcels are counted, not silently dropped from the
    /clustering/train response -- and never auto-optimized (repair is
    stubbed out here to isolate the counting logic under test)."""
    depot_id, delivery_date = "D-CMB-001", date(2026, 1, 5)
    trained_parcels = [
        FakeParcel("P-1", depot_id, delivery_date, cluster_id=0),
        FakeParcel("P-2", depot_id, delivery_date, cluster_id=0),
        FakeParcel("P-3", depot_id, delivery_date, cluster_id=-1),
    ]
    fake_result = SimpleNamespace(n_clusters=1, noise_count=1, runtime_seconds=0.01)

    async def fake_get_depot_or_fail(depot_id):
        return SimpleNamespace(lat=6.9271, lng=79.8612)

    async def fake_train_hdbscan(depot_id, delivery_date, seed=0, config=None, dataset_id=None):
        return fake_result, trained_parcels

    async def fake_repair_planning_instance(depot_id, parcels, *, depot_lat, depot_lon, seed=0):
        return None  # no vehicle catalog configured -- repair skipped, not failed

    async def fake_cluster_summary(depot_id, delivery_date, dataset_id=None):
        return {"0": 2, "-1": 1}

    monkeypatch.setattr(parcels_api, "get_depot_or_fail", fake_get_depot_or_fail)
    monkeypatch.setattr(parcels_api, "train_hdbscan", fake_train_hdbscan)
    monkeypatch.setattr(parcels_api, "repair_planning_instance", fake_repair_planning_instance)
    monkeypatch.setattr(parcels_api, "cluster_summary", fake_cluster_summary)

    response = asyncio.run(parcels_api.train_clustering(depot_id=depot_id, delivery_date=delivery_date, seed=0, dataset_id=None))

    assert response["unassigned_count"] == 1
    assert response["noise_count"] == 1
    assert response["repair"]["applied"] is False
