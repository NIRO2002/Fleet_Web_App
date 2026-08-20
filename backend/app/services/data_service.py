"""Parcel ingestion and preprocessing.

Satisfies FR01 (ingestion) and FR02 (constraint-aware preprocessing). Every
row is validated field-by-field and every failure is collected into a
structured report instead of being swallowed by a bare `except Exception`
(the defect this replaces) — the caller can see exactly which rows were
skipped and why, and which rows were accepted with a caveat.
"""
import csv
import io
import logging
from typing import Optional

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.parcel import Parcel
from app.schemas.parcel import ParcelIn

logger = logging.getLogger(__name__)

# Maps upstream/rich-dataset column names onto this schema's canonical field
# names. Columns already matching a canonical name (e.g. length_cm,
# stackable, hazardous, priority_level) need no entry here.
COLUMN_ALIASES = {
    "dropoff_lat": "latitude",
    "dropoff_lng": "longitude",
    "dropoff_latitude": "latitude",
    "dropoff_longitude": "longitude",
    "parcel_weight_kg": "weight_kg",
    "parcel_volume_m3": "volume_m3",
    "depot": "depot_id",
    "depot_code": "depot_id",
}

# Columns the optimizer *produces*, never consumes. If the upstream dataset
# includes them (e.g. a historical export), importing them would leak the
# label the research is trying to predict/optimize into the input features.
LEAKAGE_COLUMN_PREFIXES = ("load_position_",)
LEAKAGE_COLUMNS = {
    "assigned_vehicle_id",
    "assigned_route_id",
    "stop_sequence",
    "load_layer",
    "actual_delivery_time",
    "delivery_status",
    "failure_reason",
    "delivery_duration_minutes",
}

BOOLEAN_TRUE = {"1", "true", "t", "yes", "y"}
BOOLEAN_FALSE = {"0", "false", "f", "no", "n", ""}

#: Chunk size for the bulk insert/update path (F10) -- large enough to keep
#: the commit count low on a real import, small enough to keep any one
#: transaction's memory/lock footprint bounded.
BULK_CHUNK_SIZE = 2000

REQUIRED_FIELDS = ("latitude", "longitude", "weight_kg", "volume_m3")
BOOLEAN_FIELDS = (
    "fragile",
    "stackable",
    "loading_orientation_fixed",
    "hazardous",
    "requires_refrigeration",
    "two_person_lift",
    "do_not_tilt",
)


def _default_bounds() -> dict:
    return {
        "lat_min": settings.import_lat_min,
        "lat_max": settings.import_lat_max,
        "lng_min": settings.import_lng_min,
        "lng_max": settings.import_lng_max,
    }


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in BOOLEAN_TRUE:
        return True
    if text in BOOLEAN_FALSE:
        return False
    raise ValueError(f"cannot interpret '{value}' as a boolean")


def _normalize_time(value: str) -> str:
    text = str(value).strip()
    if ":" not in text:
        raise ValueError(f"'{value}' is not HH:MM")
    hour_str, minute_str, *_ = text.split(":")
    hour, minute = int(hour_str), int(minute_str)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"'{value}' is not a valid HH:MM time")
    return f"{hour:02d}:{minute:02d}"


def _map_columns(fieldnames: list[str]) -> dict[str, str]:
    return {name: COLUMN_ALIASES.get(name, name) for name in fieldnames}


def _leakage_columns_present(fieldnames: list[str]) -> set[str]:
    dropped = {
        name
        for name in fieldnames
        if name in LEAKAGE_COLUMNS or name.startswith(LEAKAGE_COLUMN_PREFIXES)
    }
    if dropped:
        logger.warning(
            "import_csv: dropping target-leakage column(s) %s - these are "
            "optimizer OUTPUTS (assigned by a previous run), not inputs, "
            "and importing them would leak the label into the feature set.",
            sorted(dropped),
        )
    return dropped


def _process_row(
    raw_row: dict,
    row_index: int,
    mapping: dict[str, str],
    leakage_columns: set[str],
    bounds: dict,
    errors: list[dict],
    warnings: list[dict],
) -> Optional[ParcelIn]:
    row: dict[str, str] = {}
    for raw_key, raw_value in raw_row.items():
        if raw_key is None or raw_key in leakage_columns:
            continue
        if raw_value is None or str(raw_value).strip() == "":
            continue
        row[mapping.get(raw_key, raw_key)] = str(raw_value).strip()

    parcel_id = row.get("parcel_id", "").strip()
    if not parcel_id:
        errors.append({"row": row_index, "field": "parcel_id", "reason": "missing parcel_id"})
        return None

    for field in REQUIRED_FIELDS:
        if not row.get(field):
            errors.append({"row": row_index, "field": field, "reason": "missing required value"})
            return None

    try:
        latitude = float(row["latitude"])
        longitude = float(row["longitude"])
        weight_kg = float(row["weight_kg"])
        volume_m3 = float(row["volume_m3"])
    except ValueError as exc:
        errors.append({"row": row_index, "field": "latitude/longitude/weight_kg/volume_m3", "reason": str(exc)})
        return None

    if not (bounds["lat_min"] <= latitude <= bounds["lat_max"] and bounds["lng_min"] <= longitude <= bounds["lng_max"]):
        warnings.append(
            {
                "row": row_index,
                "field": "latitude/longitude",
                "reason": f"({latitude}, {longitude}) is outside the configured region bounds",
            }
        )

    try:
        tw_start = _normalize_time(row.get("time_window_start", ""))
        tw_end = _normalize_time(row.get("time_window_end", ""))
    except ValueError as exc:
        errors.append({"row": row_index, "field": "time_window_start/time_window_end", "reason": str(exc)})
        return None

    dims_present = all(row.get(k) for k in ("length_cm", "width_cm", "height_cm"))
    dimensions_imputed = False
    if dims_present:
        try:
            length_cm = float(row["length_cm"])
            width_cm = float(row["width_cm"])
            height_cm = float(row["height_cm"])
        except ValueError as exc:
            errors.append({"row": row_index, "field": "length_cm/width_cm/height_cm", "reason": str(exc)})
            return None
        implied_volume = (length_cm * width_cm * height_cm) / 1e6
        if abs(implied_volume - volume_m3) > 1e-6:
            warnings.append(
                {
                    "row": row_index,
                    "field": "volume_m3",
                    "reason": f"volume_m3={volume_m3} does not match length*width*height={implied_volume:.6f}",
                }
            )
    else:
        side_cm = (volume_m3 * 1e6) ** (1 / 3)
        length_cm = width_cm = height_cm = side_cm
        dimensions_imputed = True
        warnings.append(
            {
                "row": row_index,
                "field": "length_cm/width_cm/height_cm",
                "reason": f"dimensions missing; imputed a {side_cm:.1f}cm cube from volume_m3",
            }
        )

    bool_fields: dict[str, bool] = {}
    for field in BOOLEAN_FIELDS:
        if field in row:
            try:
                bool_fields[field] = _coerce_bool(row[field])
            except ValueError as exc:
                errors.append({"row": row_index, "field": field, "reason": str(exc)})
                return None

    try:
        payload = ParcelIn(
            parcel_id=parcel_id,
            depot_id=row.get("depot_id") or None,
            delivery_date=row.get("delivery_date") or None,
            latitude=latitude,
            longitude=longitude,
            weight_kg=weight_kg,
            volume_m3=volume_m3,
            time_window_start=tw_start,
            time_window_end=tw_end,
            length_cm=length_cm,
            width_cm=width_cm,
            height_cm=height_cm,
            dimensions_imputed=dimensions_imputed,
            hazmat_class=row.get("hazmat_class") or None,
            temp_min_celsius=float(row["temp_min_celsius"]) if row.get("temp_min_celsius") else None,
            temp_max_celsius=float(row["temp_max_celsius"]) if row.get("temp_max_celsius") else None,
            priority_level=row.get("priority_level", "standard"),
            service_type=row.get("service_type", "door_to_door"),
            # Retained for source-data fidelity; placement deliberately
            # does not enforce this synthetic per-parcel field.
            max_stack_weight_kg=float(row["max_stack_weight_kg"]) if row.get("max_stack_weight_kg") else 0.0,
            **bool_fields,
        )
    except (ValueError, ValidationError) as exc:
        errors.append({"row": row_index, "field": "validation", "reason": str(exc)})
        return None

    return payload


def upsert_parcel(db: Session, payload: ParcelIn) -> Parcel:
    obj = db.query(Parcel).filter(Parcel.parcel_id == payload.parcel_id).first()
    if obj is None:
        obj = Parcel(parcel_id=payload.parcel_id)
        db.add(obj)

    for field, value in payload.model_dump(exclude={"parcel_id"}).items():
        setattr(obj, field, value)

    db.commit()
    db.refresh(obj)
    return obj


def _bulk_upsert_parcels(db: Session, payloads: list[ParcelIn]) -> tuple[int, int]:
    """Bulk insert/update path used by `import_csv` (F10). `upsert_parcel`
    ran one SELECT and one COMMIT per row — 36,000 of each on the project's
    real dataset, making the importer unusable at that scale. This instead
    preloads every existing `parcel_id` in one (chunked) query, partitions
    the payloads into inserts and updates in memory, and applies them with
    `bulk_insert_mappings`/`bulk_update_mappings` in chunks, committing once
    per chunk. `upsert_parcel` remains the single-row public API used by the
    parcel endpoint; it is never called from here. Returns `(inserted,
    updated)` counts."""
    if not payloads:
        return 0, 0

    parcel_ids = [p.parcel_id for p in payloads]
    id_by_parcel_id: dict[str, int] = {}
    for i in range(0, len(parcel_ids), BULK_CHUNK_SIZE):
        chunk = parcel_ids[i : i + BULK_CHUNK_SIZE]
        rows = db.query(Parcel.id, Parcel.parcel_id).filter(Parcel.parcel_id.in_(chunk)).all()
        id_by_parcel_id.update({parcel_id: row_id for row_id, parcel_id in rows})

    inserts: list[dict] = []
    updates: list[dict] = []
    for payload in payloads:
        data = payload.model_dump()
        existing_id = id_by_parcel_id.get(payload.parcel_id)
        if existing_id is None:
            inserts.append(data)
        else:
            data["id"] = existing_id
            updates.append(data)

    for i in range(0, len(inserts), BULK_CHUNK_SIZE):
        db.bulk_insert_mappings(Parcel, inserts[i : i + BULK_CHUNK_SIZE])
        db.commit()
    for i in range(0, len(updates), BULK_CHUNK_SIZE):
        db.bulk_update_mappings(Parcel, updates[i : i + BULK_CHUNK_SIZE])
        db.commit()

    return len(inserts), len(updates)


def import_csv(db: Session, content: bytes, bounds: dict | None = None) -> dict:
    """Import the minimal 8-column format or the full upstream dataset
    (rich column names are mapped via COLUMN_ALIASES). Never raises on a
    per-row problem — every failure is collected and returned so the caller
    can see exactly what happened, instead of a bare except swallowing it."""
    if bounds is None:
        bounds = _default_bounds()

    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    fieldnames = reader.fieldnames or []
    mapping = _map_columns(fieldnames)
    leakage_columns = _leakage_columns_present(fieldnames)

    errors: list[dict] = []
    warnings: list[dict] = []
    accepted: dict[str, ParcelIn] = {}
    duplicates_removed = 0

    for row_index, raw_row in enumerate(reader, start=2):  # header is row 1
        payload = _process_row(raw_row, row_index, mapping, leakage_columns, bounds, errors, warnings)
        if payload is None:
            continue
        if payload.parcel_id in accepted:
            duplicates_removed += 1
        accepted[payload.parcel_id] = payload  # keep the last occurrence

    inserted, updated = _bulk_upsert_parcels(db, list(accepted.values()))
    dimensions_imputed_count = sum(1 for payload in accepted.values() if payload.dimensions_imputed)

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": len(errors),
        "duplicates_removed": duplicates_removed,
        "dimensions_imputed_count": dimensions_imputed_count,
        "errors": errors,
        "warnings": warnings,
    }
