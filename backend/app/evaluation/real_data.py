"""Real parcel dataset access (Fix Pass 4 item S5).

The single place that reads `backend/data/parcels_sample_36000.csv` -- shared
by `conftest.py`'s `real_instance` fixture, the evaluation harness
(`harness.py`), and any integration test that wants real data instead of
`synthetic_data.py`. The full CSV (36,000 rows) is read once and cached, not
once per call.
"""
import functools
from pathlib import Path

import pandas as pd

DATASET_PATH = Path(__file__).resolve().parents[2] / "data" / "parcels_sample_36000.csv"

#: Columns present in the CSV with no ParcelIn equivalent -- see
#: backend/data/README.md for the full list and why they're dropped.
_NULLABLE_FLOAT_COLUMNS = ("temp_min_celsius", "temp_max_celsius")


@functools.lru_cache(maxsize=1)
def _load_full_dataset() -> pd.DataFrame:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Real dataset not found at {DATASET_PATH}. See backend/data/README.md."
        )
    return pd.read_csv(DATASET_PATH)


def list_instances() -> list[tuple[str, str]]:
    """Every `(depot_id, delivery_date)` instance key in the dataset."""
    df = _load_full_dataset()
    pairs = df[["depot_id", "delivery_date"]].drop_duplicates()
    return list(pairs.itertuples(index=False, name=None))


def real_instance_payloads(depot_id: str = "D-CMB-001", delivery_date: str = "2026-01-05") -> list[dict]:
    """One instance's parcels as `ParcelIn`-shaped payload dicts (same shape
    `synthetic_data.generate_synthetic_parcels` returns), so callers can use
    either source interchangeably. `delivery_date` matches the CSV's own
    'YYYY-MM-DD' string format."""
    df = _load_full_dataset()
    inst = df[(df["depot_id"] == depot_id) & (df["delivery_date"] == delivery_date)]
    if inst.empty:
        raise ValueError(f"No rows for depot_id={depot_id!r}, delivery_date={delivery_date!r}")

    payloads = []
    for _, row in inst.iterrows():
        payloads.append(
            {
                "parcel_id": row["parcel_id"],
                "depot_id": row["depot_id"],
                "delivery_date": row["delivery_date"],
                "latitude": float(row["dropoff_lat"]),
                "longitude": float(row["dropoff_lng"]),
                "weight_kg": float(row["weight_kg"]),
                "volume_m3": float(row["volume_m3"]),
                "length_cm": float(row["length_cm"]),
                "width_cm": float(row["width_cm"]),
                "height_cm": float(row["height_cm"]),
                # ParcelIn requires exactly HH:MM; the CSV stores HH:MM:SS.
                "time_window_start": str(row["time_window_start"])[:5],
                "time_window_end": str(row["time_window_end"])[:5],
                "fragile": bool(row["fragile"]),
                "stackable": bool(row["stackable"]),
                "max_stack_weight_kg": float(row["max_stack_weight_kg"]),
                "loading_orientation_fixed": bool(row["loading_orientation_fixed"]),
                "do_not_tilt": bool(row["do_not_tilt"]),
                "two_person_lift": bool(row["two_person_lift"]),
                "hazardous": bool(row["hazardous"]),
                "hazmat_class": row["hazmat_class"] if pd.notna(row["hazmat_class"]) else None,
                "requires_refrigeration": bool(row["requires_refrigeration"]),
                "temp_min_celsius": float(row["temp_min_celsius"]) if pd.notna(row["temp_min_celsius"]) else None,
                "temp_max_celsius": float(row["temp_max_celsius"]) if pd.notna(row["temp_max_celsius"]) else None,
                "priority_level": row["priority_level"],
                "service_type": row["service_type"],
            }
        )
    return payloads
