from pathlib import Path
import joblib
import numpy as np
import hdbscan
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.parcel import Parcel

def _minutes(value: str) -> int:
    h, m = map(int, value.split(":"))
    return h * 60 + m

def feature_matrix(parcels):
    X = []
    for p in parcels:
        X.append([
            p.latitude / 0.01,
            p.longitude / 0.01,
            p.weight_kg / 20.0,
            p.volume_m3 / 0.2,
            _minutes(p.time_window_start) / 720.0,
            _minutes(p.time_window_end) / 720.0,
            float(p.fragile),
        ])
    return np.asarray(X, dtype=float)

def train_hdbscan(db: Session):
    parcels = db.query(Parcel).all()
    if len(parcels) < settings.hdbscan_min_cluster_size:
        raise ValueError(
            f"At least {settings.hdbscan_min_cluster_size} parcels are required."
        )

    X = feature_matrix(parcels)
    model = hdbscan.HDBSCAN(
        min_cluster_size=settings.hdbscan_min_cluster_size,
        min_samples=settings.hdbscan_min_samples,
        prediction_data=True,
        metric="euclidean",
    )
    model.fit(X)

    for parcel, label, probability in zip(
        parcels, model.labels_, model.probabilities_
    ):
        parcel.cluster_id = int(label) if int(label) >= 0 else -1
        parcel.cluster_probability = float(probability)
    db.commit()

    model_dir = Path(settings.model_dir)
    model_dir.mkdir(exist_ok=True)
    joblib.dump(model, model_dir / "hdbscan_model.joblib")
    return model, parcels

def predict_cluster(payload):
    model_path = Path(settings.model_dir) / "hdbscan_model.joblib"
    if not model_path.exists():
        raise FileNotFoundError("HDBSCAN model has not been trained.")

    model = joblib.load(model_path)
    temp = type("ParcelLike", (), payload.model_dump())()
    X = feature_matrix([temp])
    labels, strengths = hdbscan.approximate_predict(model, X)
    label = int(labels[0])
    return {
        "cluster_id": label if label >= 0 else None,
        "cluster_probability": float(strengths[0]),
        "status": "ASSIGNED" if label >= 0 else "UNASSIGNED",
    }

def cluster_summary(db: Session):
    rows = db.query(Parcel.cluster_id).all()
    summary = {}
    for (cluster_id,) in rows:
        key = str(cluster_id)
        summary[key] = summary.get(key, 0) + 1
    return summary
