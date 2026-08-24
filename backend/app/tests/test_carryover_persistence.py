from datetime import date, datetime
from types import SimpleNamespace

from app.services.clustering_service import _planning_persistence_fields


def test_carryover_transition_is_part_of_cluster_persistence_update():
    parcel = SimpleNamespace(
        carried_over_from_date=date(2026, 1, 4),
        delivery_date=date(2026, 1, 5),
    )
    fields = _planning_persistence_fields(parcel, {"cluster_id": 2})
    assert fields == {
        "cluster_id": 2,
        "carried_over_from_date": datetime(2026, 1, 4),
        "delivery_date": datetime(2026, 1, 5),
    }


def test_same_day_cluster_persistence_does_not_rewrite_dates():
    parcel = SimpleNamespace(carried_over_from_date=None, delivery_date=date(2026, 1, 5))
    assert _planning_persistence_fields(parcel, {"cluster_id": 2}) == {"cluster_id": 2}
