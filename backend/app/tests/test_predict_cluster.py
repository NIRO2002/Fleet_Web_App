"""predict_cluster's joblib bundle holds only the fitted HDBSCAN model, not
the capacity-aware repair outcome that determines a parcel's actual
*persisted* cluster_id (app/services/capacity_aware_clustering.py). A raw
HDBSCAN label can silently disagree with the repaired/persisted id (splits
especially have no well-defined raw_label -> repaired_id mapping), so
predict_cluster must never return one -- see
docs/DESIGN_DECISIONS.md's "predict_cluster cannot return a post-repair
cluster_id" entry.
"""
from types import SimpleNamespace

import numpy as np

from app.services import clustering_service


class FakeParcelIn:
    """Stands in for a ParcelIn payload -- predict_cluster only needs
    `.model_dump()`."""

    def __init__(self, **fields):
        self._fields = fields

    def model_dump(self):
        return self._fields


def test_predict_cluster_never_returns_a_cluster_id(monkeypatch, tmp_path):
    model_path = tmp_path / "hdbscan_D-CMB-001_2026-01-05.joblib"
    model_path.write_bytes(b"placeholder")  # only existence is checked before joblib.load

    monkeypatch.setattr(clustering_service, "_model_path", lambda depot_id, delivery_date: model_path)
    monkeypatch.setattr(
        clustering_service.joblib, "load",
        lambda path: {"model": object(), "scaler": object(), "config": object()},
    )
    monkeypatch.setattr(clustering_service, "transform_with_scaler", lambda parcels, scaler, config: np.zeros((1, 2)))
    # A raw HDBSCAN label of 3 that would previously have been returned
    # as-is, even though it may not correspond to any real *repaired*
    # cluster (e.g. if raw cluster 3 was later split by repair).
    monkeypatch.setattr(
        clustering_service.hdbscan, "approximate_predict",
        lambda model, X: (np.array([3]), np.array([0.87])),
    )

    result = clustering_service.predict_cluster(
        FakeParcelIn(latitude=6.9, longitude=79.8, time_window_start="09:00", time_window_end="12:00"),
        "D-CMB-001", "2026-01-05",
    )

    assert result["cluster_id"] is None
    assert result["status"] == "UNASSIGNED"
    assert result["reason"] == "prediction unavailable after capacity repair"
    # The membership-strength signal is still surfaced even though the
    # cluster identity is not.
    assert result["cluster_probability"] == 0.87


def test_predict_cluster_never_returns_a_cluster_id_even_for_noise_label(monkeypatch, tmp_path):
    """Also true for a raw label of -1 (HDBSCAN's own noise sentinel) --
    the response shape must not vary with whether the raw label happened
    to be non-negative."""
    model_path = tmp_path / "hdbscan_D-CMB-001_2026-01-05.joblib"
    model_path.write_bytes(b"placeholder")

    monkeypatch.setattr(clustering_service, "_model_path", lambda depot_id, delivery_date: model_path)
    monkeypatch.setattr(
        clustering_service.joblib, "load",
        lambda path: {"model": object(), "scaler": object(), "config": object()},
    )
    monkeypatch.setattr(clustering_service, "transform_with_scaler", lambda parcels, scaler, config: np.zeros((1, 2)))
    monkeypatch.setattr(
        clustering_service.hdbscan, "approximate_predict",
        lambda model, X: (np.array([-1]), np.array([0.0])),
    )

    result = clustering_service.predict_cluster(
        FakeParcelIn(latitude=6.9, longitude=79.8, time_window_start="09:00", time_window_end="12:00"),
        "D-CMB-001", "2026-01-05",
    )

    assert result["cluster_id"] is None
    assert result["status"] == "UNASSIGNED"
