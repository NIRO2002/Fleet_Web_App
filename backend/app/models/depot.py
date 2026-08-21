from beanie import Document, Indexed


class Depot(Document):
    depot_id: Indexed(str, unique=True)
    depot_name: str
    lat: float
    lng: float
    zone_id: str
    operating_hours_start: str
    operating_hours_end: str
    vehicle_capacity: int

    class Settings:
        name = "depots"
