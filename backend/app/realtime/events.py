from app.utils_datetime import utcnow

def parcel_event(event_type: str, parcel_id: str, payload: dict) -> dict:
    return {
        "event_type": event_type,
        "parcel_id": parcel_id,
        "timestamp": utcnow().isoformat(),
        "payload": payload,
    }
