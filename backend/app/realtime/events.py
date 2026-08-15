from datetime import datetime

def parcel_event(event_type: str, parcel_id: str, payload: dict) -> dict:
    return {
        "event_type": event_type,
        "parcel_id": parcel_id,
        "timestamp": datetime.utcnow().isoformat(),
        "payload": payload,
    }
