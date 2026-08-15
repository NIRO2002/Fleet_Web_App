from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.parcel import Parcel
from app.schemas.optimization import OptimizationRequest
from app.services.optimization_service import optimize_load

router = APIRouter(prefix="/optimization", tags=["optimization"])

@router.post("/run")
def run(payload: OptimizationRequest, db: Session = Depends(get_db)):
    if payload.parcel_ids:
        parcels = db.query(Parcel).filter(Parcel.parcel_id.in_(payload.parcel_ids)).all()
    elif payload.cluster_id is not None:
        parcels = db.query(Parcel).filter(Parcel.cluster_id == payload.cluster_id).all()
    else:
        raise HTTPException(status_code=400, detail="Provide cluster_id or parcel_ids")

    if not parcels:
        raise HTTPException(status_code=404, detail="No matching parcels")

    try:
        depot_lat = payload.depot_latitude or settings.depot_latitude
        depot_lon = payload.depot_longitude or settings.depot_longitude
        result, _ = optimize_load(db, parcels, depot_lat, depot_lon)
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
