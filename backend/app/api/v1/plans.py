from fastapi import APIRouter
from app.models.load_plan import LoadPlan

router = APIRouter(prefix="/plans", tags=["plans"])

@router.get("")
async def list_plans():
    rows = await LoadPlan.find_all().sort("-created_at").to_list()
    return [{"plan_id": p.plan_id, "depot_id": p.depot_id, "delivery_date": p.delivery_date, "created_at": p.created_at, "vehicle_count": p.n_vehicles, "feasible": p.excluded_infeasible_cluster_count == 0} for p in rows]
