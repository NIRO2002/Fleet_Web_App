from app.models.depot import Depot


DEPOTS = (
    dict(depot_id="D-CMB-001", depot_name="Colombo Central Distribution Hub", lat=6.927079, lng=79.861244, zone_id="Z-CMB-001", operating_hours_start="06:00", operating_hours_end="22:00", vehicle_capacity=95),
    dict(depot_id="D-CMB-002", depot_name="Nugegoda Urban Fulfilment Depot", lat=6.864908, lng=79.899678, zone_id="Z-CMB-007", operating_hours_start="06:30", operating_hours_end="21:30", vehicle_capacity=70),
    dict(depot_id="D-CMB-003", depot_name="Dehiwala South Logistics Depot", lat=6.851320, lng=79.865576, zone_id="Z-CMB-008", operating_hours_start="07:00", operating_hours_end="21:00", vehicle_capacity=58),
)


async def seed_depots() -> None:
    for row in DEPOTS:
        depot = await Depot.find_one({"depot_id": row["depot_id"]})
        if depot is None:
            await Depot(**row).insert()
        else:
            await depot.set(row)
