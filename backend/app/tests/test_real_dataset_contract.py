from pathlib import Path

import pandas as pd
import pytest

import app.evaluation.real_data as real_data


def test_bundled_real_dataset_has_exact_experiment_shape():
    frame = real_data._load_full_dataset()
    real_data.validate_real_dataset(frame)
    assert len(frame) == 36_000
    assert len(real_data.list_instances()) == 90
    assert frame["depot_id"].nunique() == 3


def test_missing_real_dataset_never_falls_back_to_synthetic(monkeypatch, tmp_path):
    monkeypatch.setattr(real_data, "DATASET_PATH", tmp_path / "absent.csv")
    real_data._load_full_dataset.cache_clear()
    try:
        with pytest.raises(FileNotFoundError, match="Real dataset not found"):
            real_data.real_instance_payloads()
    finally:
        real_data._load_full_dataset.cache_clear()


def test_malformed_real_dataset_is_rejected(monkeypatch, tmp_path):
    malformed = tmp_path / "malformed.csv"
    pd.DataFrame([
        {"parcel_id": "P-1", "depot_id": "D-1", "delivery_date": "2026-01-01"},
    ]).to_csv(malformed, index=False)
    monkeypatch.setattr(real_data, "DATASET_PATH", Path(malformed))
    real_data._load_full_dataset.cache_clear()
    try:
        with pytest.raises(ValueError, match="36,000 rows"):
            real_data.list_instances()
    finally:
        real_data._load_full_dataset.cache_clear()
