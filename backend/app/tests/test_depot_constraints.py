import asyncio
from types import SimpleNamespace

import pytest

from app.services import depot_service


def test_unknown_depot_fails_without_global_fallback(monkeypatch):
    async def missing(_query):
        return None

    monkeypatch.setattr(depot_service.Depot, "find_one", missing)
    with pytest.raises(ValueError, match="no coordinate fallback"):
        asyncio.run(depot_service.get_depot_or_fail("UNKNOWN"))


def test_authoritative_depot_fleet_ceilings_are_positive():
    from app.db.seed_depots import DEPOTS

    assert {row["depot_id"]: row["vehicle_capacity"] for row in DEPOTS} == {
        "D-CMB-001": 95,
        "D-CMB-002": 70,
        "D-CMB-003": 58,
    }
    from app.services.optimization_service import _enforce_depot_vehicle_capacity
    _enforce_depot_vehicle_capacity(58, 58)
    with pytest.raises(ValueError, match="fleet capacity"):
        _enforce_depot_vehicle_capacity(59, 58)
