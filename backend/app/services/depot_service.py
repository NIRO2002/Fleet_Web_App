from app.models.depot import Depot


async def get_depot_or_fail(depot_id: str) -> Depot:
    depot = await Depot.find_one({"depot_id": depot_id})
    if depot is None:
        raise ValueError(f"Unknown depot_id={depot_id!r}; no coordinate fallback is permitted.")
    return depot
