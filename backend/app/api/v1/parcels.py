from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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
    return dict(zip(("inserted", "skipped"), import_csv(db, await file.read())))

@router.post("/clustering/train")
def train_clustering(db: Session = Depends(get_db)):
    try:
        model, parcels = train_hdbscan(db)
        return {"status": "trained", "parcel_count": len(parcels), "clusters": cluster_summary(db)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.get("/clustering")
def get_clusters(db: Session = Depends(get_db)):
    return cluster_summary(db)

@router.post("/clustering/predict")
def predict_new_parcel(payload: ClusterPredictionRequest):
    try:
        return predict_cluster(payload.parcel)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
