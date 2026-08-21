import asyncio
from datetime import date
from pathlib import Path

from app.services import data_service


CSV_HEADER = (
    "parcel_id,latitude,longitude,weight_kg,volume_m3,"
    "time_window_start,time_window_end\n"
)


def test_minimal_csv_uses_instance_defaults_and_reports_counts(monkeypatch):
    captured = []

    async def fake_upsert(payloads):
        captured.extend(payloads)
        return len(payloads), 0

    monkeypatch.setattr(data_service, "_bulk_upsert_parcels", fake_upsert)
    rows = "".join(
        f"P-{number},6.9271,79.8612,2.5,0.01,08:00,12:00\n"
        for number in range(1, 4)
    )

    result = asyncio.run(
        data_service.import_csv(
            (CSV_HEADER + rows).encode(),
            default_depot_id="D-CMB-001",
            default_delivery_date=date(2026, 1, 5),
            dataset_id="IMPORT-THREE",
        )
    )

    assert result["total_rows"] == 3
    assert result["processed"] == 3
    assert result["inserted"] == 3
    assert result["updated"] == result["failed"] == result["skipped"] == 0
    assert all(parcel.depot_id == "D-CMB-001" for parcel in captured)
    assert all(parcel.delivery_date == date(2026, 1, 5) for parcel in captured)
    assert all(parcel.dataset_id == "IMPORT-THREE" for parcel in captured)
    assert result["dataset_id"] == "IMPORT-THREE"


def test_explicit_csv_instance_is_not_overridden(monkeypatch):
    captured = []

    async def fake_upsert(payloads):
        captured.extend(payloads)
        return 0, len(payloads)

    monkeypatch.setattr(data_service, "_bulk_upsert_parcels", fake_upsert)
    content = (
        "parcel_id,depot_id,delivery_date,latitude,longitude,weight_kg,volume_m3,"
        "time_window_start,time_window_end\n"
        "P-EXPLICIT,D-JAF-001,2026-02-01,9.6615,80.0255,2.5,0.01,08:00,12:00\n"
    ).encode()

    result = asyncio.run(
        data_service.import_csv(
            content,
            default_depot_id="D-CMB-001",
            default_delivery_date=date(2026, 1, 5),
        )
    )

    assert result["inserted"] == 0
    assert result["updated"] == 1
    assert captured[0].depot_id == "D-JAF-001"
    assert captured[0].delivery_date == date(2026, 2, 1)


def test_header_whitespace_and_case_are_normalized(monkeypatch):
    async def fake_upsert(payloads):
        return len(payloads), 0

    monkeypatch.setattr(data_service, "_bulk_upsert_parcels", fake_upsert)
    content = (
        " Parcel_ID , Latitude , Longitude , Weight_Kg , Volume_M3 ,"
        " Time_Window_Start , Time_Window_End \n"
        "P-NORMALIZED,6.9271,79.8612,1,0.01,08:00,12:00\n"
    ).encode()

    result = asyncio.run(data_service.import_csv(content))

    assert result["processed"] == result["inserted"] == 1
    assert result["failed"] == 0


def test_real_36000_row_dataset_is_accepted(monkeypatch):
    captured = []

    async def fake_upsert(payloads):
        captured.extend(payloads)
        return len(payloads), 0

    monkeypatch.setattr(data_service, "_bulk_upsert_parcels", fake_upsert)
    dataset = Path(__file__).parents[2] / "data" / "parcels_sample_36000.csv"

    result = asyncio.run(data_service.import_csv(dataset.read_bytes()))

    assert result["total_rows"] == 36_000
    assert result["processed"] == result["inserted"] == 36_000
    assert result["failed"] == 0
    assert sum(
        parcel.depot_id == "D-CMB-001"
        and parcel.delivery_date == date(2026, 1, 5)
        for parcel in captured
    ) == 400
