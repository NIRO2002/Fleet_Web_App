import asyncio
from datetime import date, datetime

from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from app.models.parcel import Parcel
from app.services.data_service import _mongo_update_fields, import_csv


def _parcel(parcel_id: str, **overrides) -> Parcel:
    values = {
        "parcel_id": parcel_id,
        "depot_id": "D-CMB-001",
        "delivery_date": date(2026, 1, 5),
        "latitude": 6.9271,
        "longitude": 79.8612,
        "weight_kg": 2.5,
        "volume_m3": 0.01,
        "time_window_start": "08:00",
        "time_window_end": "12:00",
    }
    values.update(overrides)
    return Parcel(**values)


async def _init_database(name: str):
    client = AsyncMongoMockClient()
    await init_beanie(database=client[name], document_models=[Parcel])
    return client[name]


def test_parcel_dates_round_trip_bulk_import_update_and_query(monkeypatch):
    async def scenario():
        database = await _init_database("parcel_date_regression")

        # mongomock 4.3 does not yet accept PyMongo 4.17's new bulk-update
        # ``sort`` keyword. Execute the generated UpdateOne operations one by
        # one while preserving the production bulk-write encoding boundary.
        collection = Parcel.get_motor_collection()
        async def compatible_bulk_write(operations):
            for operation in operations:
                await collection.update_one(operation._filter, operation._doc)
        monkeypatch.setattr(collection, "bulk_write", compatible_bulk_write)

        single = _parcel("P-SINGLE")
        original_created_at = single.created_at
        await single.insert()
        raw = await database.parcels.find_one({"parcel_id": "P-SINGLE"})
        assert isinstance(raw["delivery_date"], datetime)
        assert raw["delivery_date"] == datetime(2026, 1, 5)
        assert raw["created_at"] == original_created_at.replace(
            tzinfo=None, microsecond=(original_created_at.microsecond // 1000) * 1000
        )
        assert (await Parcel.find_one(Parcel.parcel_id == "P-SINGLE")).delivery_date == date(2026, 1, 5)

        await Parcel.insert_many([_parcel("P-BULK-1"), _parcel("P-BULK-2")])

        csv = (
            "parcel_id,depot_id,delivery_date,latitude,longitude,weight_kg,volume_m3,"
            "time_window_start,time_window_end\n"
            "P-CSV,D-CMB-001,2026-01-05,6.9271,79.8612,2.5,0.01,08:00,12:00\n"
        ).encode()
        first = await import_csv(csv)
        second = await import_csv(csv)
        assert (first["inserted"], first["updated"]) == (1, 0)
        assert (second["inserted"], second["updated"]) == (0, 1)

        carried = _parcel("P-CARRY", carried_over_from_date=date(2026, 1, 4))
        await carried.insert()
        fields = _mongo_update_fields(carried)
        assert fields["delivery_date"] == datetime(2026, 1, 5)
        assert fields["carried_over_from_date"] == datetime(2026, 1, 4)
        await database.parcels.update_one(
            {"parcel_id": "P-CARRY"}, {"$set": fields}
        )
        restored = await Parcel.find_one(Parcel.parcel_id == "P-CARRY")
        assert restored.delivery_date == date(2026, 1, 5)
        assert restored.carried_over_from_date == date(2026, 1, 4)

        rows = await Parcel.find({
            "depot_id": "D-CMB-001", "delivery_date": date(2026, 1, 5)
        }).to_list()
        assert {row.parcel_id for row in rows} >= {
            "P-SINGLE", "P-BULK-1", "P-BULK-2", "P-CSV", "P-CARRY"
        }

    asyncio.run(scenario())
