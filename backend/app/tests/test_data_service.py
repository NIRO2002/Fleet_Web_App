"""Phase 1 gate: the rich upstream format imports successfully, and a
deliberately corrupted fixture produces a non-empty, accurate error report
instead of being silently swallowed by a bare `except Exception`."""
from app.services.data_service import import_csv


def test_rich_format_import_maps_columns_and_drops_leakage_columns(db_session):
    csv_content = (
        "parcel_id,dropoff_lat,dropoff_lng,weight_kg,volume_m3,"
        "time_window_start,time_window_end,fragile,length_cm,width_cm,height_cm,"
        "stackable,hazardous,requires_refrigeration,priority_level,"
        "assigned_vehicle_id,load_position_x\n"
        "R001,6.9271,79.8612,2.5,0.015,10:00,13:00,false,25,15,10,"
        "true,false,false,express,VV-LEAKED,42\n"
    ).encode("utf-8")

    report = import_csv(db_session, csv_content)

    assert report["inserted"] == 1
    assert report["skipped"] == 0
    assert report["errors"] == []

    from app.models.parcel import Parcel

    parcel = db_session.query(Parcel).filter(Parcel.parcel_id == "R001").first()
    assert parcel is not None
    assert parcel.latitude == 6.9271
    assert parcel.longitude == 79.8612
    assert parcel.priority_level == "express"
    assert parcel.length_cm == 25


def test_corrupted_fixture_produces_accurate_error_report(db_session):
    csv_content = (
        "parcel_id,latitude,longitude,weight_kg,volume_m3,"
        "time_window_start,time_window_end,fragile\n"
        # valid row
        "OK001,6.9271,79.8612,2.5,0.015,10:00,13:00,false\n"
        # missing parcel_id
        ",6.9271,79.8612,2.5,0.015,10:00,13:00,false\n"
        # missing latitude
        "BAD002,,79.8612,2.5,0.015,10:00,13:00,false\n"
        # invalid time format
        "BAD003,6.9271,79.8612,2.5,0.015,25:99,13:00,false\n"
        # out of region (warning, not an error - still inserted)
        "WARN004,1.0,1.0,2.5,0.015,10:00,13:00,false\n"
        # duplicate of OK001, last one wins
        "OK001,6.93,79.87,3.0,0.02,11:00,14:00,true\n"
    ).encode("utf-8")

    report = import_csv(db_session, csv_content)

    assert report["errors"], "expected a non-empty error report for the corrupted fixture"
    assert report["skipped"] == 3  # missing parcel_id, missing latitude, invalid time

    error_fields = {e["field"] for e in report["errors"]}
    assert "parcel_id" in error_fields
    assert "latitude" in error_fields

    assert report["duplicates_removed"] == 1
    assert any(w["field"] == "latitude/longitude" for w in report["warnings"])

    from app.models.parcel import Parcel

    ok = db_session.query(Parcel).filter(Parcel.parcel_id == "OK001").first()
    assert ok.weight_kg == 3.0  # last occurrence won


def test_dimension_volume_mismatch_is_a_warning_not_a_rejection(db_session):
    csv_content = (
        "parcel_id,latitude,longitude,weight_kg,volume_m3,"
        "time_window_start,time_window_end,fragile,length_cm,width_cm,height_cm\n"
        "MISMATCH01,6.9271,79.8612,2.5,0.015,10:00,13:00,false,100,100,100\n"
    ).encode("utf-8")

    report = import_csv(db_session, csv_content)

    assert report["inserted"] == 1
    assert report["skipped"] == 0
    assert any(w["field"] == "volume_m3" for w in report["warnings"])


def test_missing_dimensions_are_imputed_as_a_cube_and_flagged(db_session):
    csv_content = (
        "parcel_id,latitude,longitude,weight_kg,volume_m3,"
        "time_window_start,time_window_end,fragile\n"
        "NODIM01,6.9271,79.8612,2.5,0.008,10:00,13:00,false\n"
    ).encode("utf-8")

    report = import_csv(db_session, csv_content)

    assert report["inserted"] == 1
    assert any(w["field"] == "length_cm/width_cm/height_cm" for w in report["warnings"])

    from app.models.parcel import Parcel

    parcel = db_session.query(Parcel).filter(Parcel.parcel_id == "NODIM01").first()
    assert parcel.length_cm == parcel.width_cm == parcel.height_cm
    assert round(parcel.length_cm, 1) == 20.0  # cbrt(0.008 m^3 * 1e6 cm^3) = 20cm
