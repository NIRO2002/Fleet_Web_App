from datetime import date
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from app.models.parcel import Parcel
from app.schemas.parcel import (
    ParcelCreate, ParcelIn, ParcelResponse, ClusterPredictionRequest, CSVUploadResponse
)
from app.services.data_service import create_parcel as create_parcel_record, import_csv
from app.services.clustering_service import predict_cluster, train_hdbscan, cluster_summary
from app.services.clustering_common import ClusteringConfig
from app.services.depot_service import get_depot_or_fail

router = APIRouter(prefix="/parcels", tags=["parcels"])

@router.post("", response_model=ParcelResponse, status_code=201)
async def create_parcel(payload: ParcelCreate):
    created = await create_parcel_record(payload)
    if created is None:
        raise HTTPException(status_code=409, detail="Parcel ID already exists")
    return created

@router.get("")
async def list_parcels(
    depot_id: str | None = Query(default=None),
    delivery_date: date | None = Query(default=None),
    dataset_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    paginated: bool = Query(default=False),
):
    filters = {}
    if depot_id is not None:
        filters["depot_id"] = depot_id
    if delivery_date is not None:
        filters["delivery_date"] = delivery_date
    if dataset_id is not None:
        filters["dataset_id"] = dataset_id
    if not paginated:
        return await Parcel.find(filters).sort("-created_at").to_list()
    total = await Parcel.find(filters).count()
    items = await Parcel.find(filters).sort("-created_at").skip(offset).limit(limit).to_list()
    return {"items": items, "total": total, "limit": limit, "offset": offset}

@router.post("/upload-csv", response_model=CSVUploadResponse)
async def upload_csv(
    file: UploadFile = File(...),
    depot_id: str | None = Query(default=None),
    delivery_date: date | None = Query(default=None),
):
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV file required")
    content = await file.read()
    dataset_id = f"IMPORT-{uuid4().hex}"
    result = await import_csv(
        content,
        default_depot_id=depot_id,
        default_delivery_date=delivery_date,
        dataset_id=dataset_id,
    )
    return result

@router.post("/clustering/train")
async def train_clustering(
    depot_id: str = Query(...),
    delivery_date: date = Query(...),
    seed: int = Query(default=0),
    dataset_id: str | None = Query(default=None),
):
    """Trains HDBSCAN on exactly one (depot_id, delivery_date) planning
    instance - never the whole parcels table. See
    app/services/clustering_service.py."""
    try:
        if dataset_id is None:
            depot = await get_depot_or_fail(depot_id)
            result, parcels = await train_hdbscan(
                depot_id,
                delivery_date,
                seed=seed,
                config=ClusteringConfig(depot_lat=depot.lat, depot_lon=depot.lng),
            )
            n_clusters = result.n_clusters
            noise_count = result.noise_count
            runtime_seconds = result.runtime_seconds
        else:
            dataset_rows = await Parcel.find({"dataset_id": dataset_id}).to_list()
            instances = sorted({
                (row.depot_id, row.delivery_date)
                for row in dataset_rows
                if row.depot_id is not None and row.delivery_date is not None
            })
            if not instances:
                raise ValueError("The active dataset has no valid depot/date planning instances.")
            parcels = []
            n_clusters = 0
            noise_count = 0
            runtime_seconds = 0.0
            label_offset = 0
            for instance_depot, instance_date in instances:
                depot = await get_depot_or_fail(instance_depot)
                instance_result, instance_parcels = await train_hdbscan(
                    instance_depot,
                    instance_date,
                    seed=seed,
                    dataset_id=dataset_id,
                    label_offset=label_offset,
                    config=ClusteringConfig(depot_lat=depot.lat, depot_lon=depot.lng),
                )
                parcels.extend(instance_parcels)
                n_clusters += instance_result.n_clusters
                noise_count += instance_result.noise_count
                runtime_seconds += instance_result.runtime_seconds
                label_offset += instance_result.n_clusters
        return {
            "status": "trained",
            "parcel_count": len(parcels),
            "n_clusters": n_clusters,
            "noise_count": noise_count,
            "runtime_seconds": runtime_seconds,
            "clusters": await cluster_summary(depot_id, delivery_date, dataset_id=dataset_id),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.get("/clustering")
async def get_clusters(
    depot_id: str = Query(...),
    delivery_date: date = Query(...),
    dataset_id: str | None = Query(default=None),
):
    return await cluster_summary(depot_id, delivery_date, dataset_id=dataset_id)

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
