import asyncio
from types import SimpleNamespace

from app.schemas.parcel import ParcelCreate
from app.services import data_service


def payload():
    return ParcelCreate(
        parcel_id="P-PUBLIC", dataset_id="DAY-1", depot_id="D-CMB-002",
        delivery_date="2026-01-05", latitude=6.86, longitude=79.89,
        weight_kg=4.2, volume_m3=0.03, time_window_start="09:00",
        time_window_end="11:00", fragile=True, stackable=False,
        length_cm=50, width_cm=30, height_cm=20, priority_level="express",
        service_type="door_to_door",
    )


def test_public_create_schema_excludes_pipeline_owned_fields():
    fields = ParcelCreate.model_fields
    assert not {"dimensions_imputed", "status", "is_noise", "cluster_id", "cluster_probability", "plan_id", "carried_over_from_date"} & fields.keys()


def test_create_parcel_does_not_overwrite_duplicate(monkeypatch):
    existing = SimpleNamespace(parcel_id="P-PUBLIC", weight_kg=99)

    class FakeParcel:
        parcel_id = "parcel_id"
        @classmethod
        async def find_one(cls, _query): return existing

    monkeypatch.setattr(data_service, "Parcel", FakeParcel)
    assert asyncio.run(data_service.create_parcel(payload())) is None
    assert existing.weight_kg == 99
