"""Canonical BSON encoding for business-layer calendar dates."""
from datetime import date, datetime, time
from typing import Any

from beanie.odm.utils.encoder import Encoder


def date_to_bson(value: date) -> datetime:
    """Store a calendar date as a timezone-naive BSON datetime at midnight."""
    return datetime.combine(value, time.min)


# ``datetime`` subclasses ``date``. Its exact-type identity entry prevents
# Beanie's subclass lookup from passing real timestamps through date_to_bson.
DATE_BSON_ENCODERS = {datetime: lambda value: value, date: date_to_bson}


def to_bson_safe(value: Any) -> Any:
    """Encode values used in raw PyMongo operations like Beanie does."""
    return Encoder(custom_encoders=DATE_BSON_ENCODERS, to_db=True).encode(value)


def encode_mongo_document(document: Any) -> dict:
    """Encode a Beanie document using its configured BSON encoders."""
    return Encoder(
        custom_encoders=document.get_settings().bson_encoders,
        to_db=True,
    ).encode(document)
