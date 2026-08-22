from pydantic import BaseModel

class ParcelAssignment(BaseModel):
    plan_id: str | None = None
    virtual_vehicle_id: str | None = None
    parcel_id: str
    delivery_sequence: int
    load_sequence: int
    stack_layer: int = 0
    load_position_x: float = 0.0
    load_position_y: float = 0.0
    load_position_z: float = 0.0
    placed_length_cm: float | None = None
    placed_width_cm: float | None = None
    placed_height_cm: float | None = None
