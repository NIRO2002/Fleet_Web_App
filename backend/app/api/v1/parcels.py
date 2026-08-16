from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.parcel import Parcel
from app.schemas.parcel import (
    ParcelIn, ParcelResponse, ClusterPredictionRequest, CSVUploadResponse
)
from app.services.data_service import upsert_parcel, import_csv
from app.services.clustering_service import predict_cluster, train_hdbscan, cluster_summary

router = APIRouter(prefix="/parcels", tags=["parcels"])

@router.post("", response_model=ParcelResponse)
def create_parcel(payload: ParcelIn, db: Session = Depends(get_db)):
    return upsert_parcel(db, payload)

@router.get("", response_model=list[ParcelResponse])
def list_parcels(db: Session = Depends(get_db)):
    return db.query(Parcel).order_by(Parcel.created_at.desc()).all()

@router.post("/upload-csv", response_model=CSVUploadResponse)
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV file required")
    return import_csv(db, await file.read())

@router.post("/clustering/train")
def train_clustering(
    depot_id: str = Query(...),
    delivery_date: date = Query(...),
    seed: int = Query(default=0),
    db: Session = Depends(get_db),
):
    """Trains HDBSCAN on exactly one (depot_id, delivery_date) planning
    instance — never the whole parcels table. See
    app/services/clustering_service.py."""
    try:
        result, parcels = train_hdbscan(db, depot_id, delivery_date, seed=seed)
        return {
            "status": "trained",
            "parcel_count": len(parcels),
            "n_clusters": result.n_clusters,
            "noise_count": result.noise_count,
            "runtime_seconds": result.runtime_seconds,
            "clusters": cluster_summary(db, depot_id, delivery_date),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.get("/clustering")
def get_clusters(
    depot_id: str = Query(...),
    delivery_date: date = Query(...),
    db: Session = Depends(get_db),
):
    return cluster_summary(db, depot_id, delivery_date)

@router.post("/clustering/predict")
def predict_new_parcel(
    payload: ClusterPredictionRequest,
    depot_id: str = Query(...),
    delivery_date: date = Query(...),
):
    try:
        return predict_cluster(payload.parcel, depot_id, delivery_date)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
