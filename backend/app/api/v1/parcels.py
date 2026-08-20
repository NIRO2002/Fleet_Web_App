from datetime import date

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from app.models.parcel import Parcel
from app.schemas.parcel import (
    ParcelIn, ParcelResponse, ClusterPredictionRequest, CSVUploadResponse
)
from app.services.data_service import upsert_parcel, import_csv
from app.services.clustering_service import predict_cluster, train_hdbscan, cluster_summary

router = APIRouter(prefix="/parcels", tags=["parcels"])

@router.post("", response_model=ParcelResponse)
async def create_parcel(payload: ParcelIn):
    return await upsert_parcel(payload)

@router.get("", response_model=list[ParcelResponse])
async def list_parcels(
    depot_id: str | None = Query(default=None),
    delivery_date: date | None = Query(default=None),
):
    filters = {}
    if depot_id is not None:
        filters["depot_id"] = depot_id
    if delivery_date is not None:
        filters["delivery_date"] = delivery_date
    return await Parcel.find(filters).sort("-created_at").to_list()

@router.post("/upload-csv", response_model=CSVUploadResponse)
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV file required")
    return await import_csv(await file.read())

@router.post("/clustering/train")
async def train_clustering(
    depot_id: str = Query(...),
    delivery_date: date = Query(...),
    seed: int = Query(default=0),
):
    """Trains HDBSCAN on exactly one (depot_id, delivery_date) planning
    instance — never the whole parcels table. See
    app/services/clustering_service.py."""
    try:
        result, parcels = await train_hdbscan(depot_id, delivery_date, seed=seed)
        return {
            "status": "trained",
            "parcel_count": len(parcels),
            "n_clusters": result.n_clusters,
            "noise_count": result.noise_count,
            "runtime_seconds": result.runtime_seconds,
            "clusters": await cluster_summary(depot_id, delivery_date),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.get("/clustering")
async def get_clusters(
    depot_id: str = Query(...),
    delivery_date: date = Query(...),
):
    return await cluster_summary(depot_id, delivery_date)

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
