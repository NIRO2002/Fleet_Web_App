import asyncio
from copy import deepcopy
from datetime import date
from types import SimpleNamespace

from app.services import clustering_common


class Query:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self):
        return self.rows


class StoredParcel(SimpleNamespace):
    save_calls = 0

    def model_copy(self, deep=False):
        return deepcopy(self)

    async def save(self):
        type(self).save_calls += 1


def test_planning_instance_loader_is_read_only(monkeypatch):
    target = date(2026, 1, 5)
    same_day = StoredParcel(parcel_id="TODAY", delivery_date=target)
    old_date = date(2026, 1, 4)
    carryover = StoredParcel(parcel_id="OLD", delivery_date=old_date)

    class FakeParcel:
        calls = 0

        @classmethod
        def find(cls, _filters):
            cls.calls += 1
            return Query([same_day] if cls.calls == 1 else [carryover])

    monkeypatch.setattr(clustering_common, "Parcel", FakeParcel)
    StoredParcel.save_calls = 0

    loaded = asyncio.run(clustering_common.get_planning_instance("D-CMB-001", target))

    assert StoredParcel.save_calls == 0
    assert carryover.delivery_date == old_date
    projected = next(parcel for parcel in loaded if parcel.parcel_id == "OLD")
    assert projected.delivery_date == target
    assert projected.carried_over_from_date == old_date
