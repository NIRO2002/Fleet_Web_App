from datetime import date
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from app.models.parcel import Parcel
from app.schemas.parcel import (
    ParcelCreate, ParcelIn, ParcelResponse, ClusterPredictionRequest, CSVUploadResponse
)
from app.services.data_service import create_parcel as create_parcel_record, import_csv
from app.services.clustering_service import predict_cluster, train_hdbscan, cluster_summary, repair_planning_instance
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
    instance - never the whole parcels table - then runs capacity-aware
    repair against that instance's vehicle catalog (skipped, not failed, if
    the depot has no active vehicle types yet). This is the same
    HDBSCAN -> repair pipeline app/evaluation/harness.py exercises for
    evaluation; NSGA-II is the caller's separate, explicit next step via
    POST /optimization/run. See app/services/clustering_service.py."""
    try:
        repair_applied = False
        n_split = n_merged = excluded_infeasible_count = 0
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
            repaired = await repair_planning_instance(
                depot_id, parcels, depot_lat=depot.lat, depot_lon=depot.lng, seed=seed,
            )
            if repaired is not None:
                repair_applied = True
                n_split, n_merged = repaired.n_split, repaired.n_merged
                excluded_infeasible_count = repaired.excluded_infeasible_count
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
            for instance_depot, instance_date in instances:
                depot = await get_depot_or_fail(instance_depot)
                instance_result, instance_parcels = await train_hdbscan(
                    instance_depot,
                    instance_date,
                    seed=seed,
                    dataset_id=dataset_id,
                    config=ClusteringConfig(depot_lat=depot.lat, depot_lon=depot.lng),
                )
                parcels.extend(instance_parcels)
                n_clusters += instance_result.n_clusters
                noise_count += instance_result.noise_count
                runtime_seconds += instance_result.runtime_seconds
                repaired = await repair_planning_instance(
                    instance_depot, instance_parcels, depot_lat=depot.lat, depot_lon=depot.lng, seed=seed,
                )
                if repaired is not None:
                    repair_applied = True
                    n_split += repaired.n_split
                    n_merged += repaired.n_merged
                    excluded_infeasible_count += repaired.excluded_infeasible_count
        # Final, post-repair count of parcels left genuinely unassignable
        # (cluster_id still -1) -- smaller than noise_count, which is
        # HDBSCAN's raw pre-reassignment noise, since repair gets a second,
        # capacity-aware chance to merge noise-origin parcels into a real
        # cluster (see repair_planning_instance). Surfaced so the UI can
        # show it; these parcels are never auto-optimized (see
        # GET /parcels/clustering/unassigned).
        unassigned_count = sum(1 for p in parcels if p.cluster_id == -1)
        return {
            "status": "trained",
            "parcel_count": len(parcels),
            "n_clusters": n_clusters,
            "noise_count": noise_count,
            "unassigned_count": unassigned_count,
            "runtime_seconds": runtime_seconds,
            "repair": {
                "applied": repair_applied,
                "n_split": n_split,
                "n_merged": n_merged,
                "excluded_infeasible_count": excluded_infeasible_count,
            },
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

@router.get("/clustering/unassigned")
async def list_unassigned_parcels(
    depot_id: str = Query(...),
    delivery_date: date = Query(...),
):
    """Parcels HDBSCAN could not cluster and neither handle_noise
    (app/services/clustering_common.py) nor capacity-aware repair could
    place into a real, feasible cluster -- left honestly at cluster_id=-1
    rather than silently dropped. Never auto-optimized; surfaced so a human
    can decide what to do with them (retry with different params, manual
    routing, etc.).

    Scoped to status=PENDING to match get_planning_instance -- the same
    definition of "this planning instance" that training/repair itself
    used, so this count agrees with /clustering/train's unassigned_count.
    A PLANNED/DELIVERED/FAILED parcel that happens to carry a stale
    cluster_id=-1 from before it left PENDING isn't awaiting attention
    anymore and would otherwise show up here misleadingly."""
    return await Parcel.find({
        "depot_id": depot_id,
        "delivery_date": delivery_date,
        "cluster_id": -1,
        "status": "PENDING",
    }).to_list()

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
