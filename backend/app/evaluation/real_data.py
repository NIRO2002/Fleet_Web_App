"""Validated access to the immutable 36,000-row evaluation CSV."""
import functools
from pathlib import Path

import pandas as pd

DATASET_PATH = Path(__file__).resolve().parents[2] / "data" / "parcels_sample_36000.csv"
EXPECTED_ROWS, EXPECTED_INSTANCES, EXPECTED_PARCELS_PER_INSTANCE = 36_000, 90, 400


def validate_real_dataset(frame):
    missing = {"parcel_id", "depot_id", "delivery_date"} - set(frame.columns)
    if missing:
        raise ValueError(f"Real dataset is missing required columns: {sorted(missing)}")
    sizes = frame.groupby(["depot_id", "delivery_date"]).size()
    if len(frame) != EXPECTED_ROWS or len(sizes) != EXPECTED_INSTANCES or (sizes != EXPECTED_PARCELS_PER_INSTANCE).any():
        raise ValueError("Real dataset must contain 90 depot/date instances of exactly 400 parcels (36,000 rows).")


@functools.lru_cache(maxsize=1)
def load_full_dataset():
    frame = pd.read_csv(DATASET_PATH)
    validate_real_dataset(frame)
    return frame


def list_instances():
    return list(load_full_dataset()[["depot_id", "delivery_date"]].drop_duplicates().itertuples(index=False, name=None))
