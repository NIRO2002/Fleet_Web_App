import csv
import io
from sqlalchemy.orm import Session

from app.models.parcel import Parcel
from app.schemas.parcel import ParcelIn

def upsert_parcel(db: Session, payload: ParcelIn) -> Parcel:
    obj = db.query(Parcel).filter(Parcel.parcel_id == payload.parcel_id).first()
    if obj is None:
        obj = Parcel(parcel_id=payload.parcel_id)
        db.add(obj)

    for field in (
        "latitude", "longitude", "weight_kg", "volume_m3",
        "time_window_start", "time_window_end", "fragile"
    ):
        setattr(obj, field, getattr(payload, field))

    db.commit()
    db.refresh(obj)
    return obj

def import_csv(db: Session, content: bytes):
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    required = {
        "parcel_id", "latitude", "longitude", "weight_kg", "volume_m3",
        "time_window_start", "time_window_end", "fragile"
    }
    if not required.issubset(set(reader.fieldnames or [])):
        raise ValueError(f"CSV must contain: {sorted(required)}")

    inserted = skipped = 0
    for row in reader:
        try:
            payload = ParcelIn(
                parcel_id=row["parcel_id"].strip(),
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                weight_kg=float(row["weight_kg"]),
                volume_m3=float(row["volume_m3"]),
                time_window_start=row["time_window_start"].strip(),
                time_window_end=row["time_window_end"].strip(),
                fragile=str(row["fragile"]).strip().lower() in {"1", "true", "yes"},
            )
            upsert_parcel(db, payload)
            inserted += 1
        except Exception:
            skipped += 1
    return inserted, skipped
