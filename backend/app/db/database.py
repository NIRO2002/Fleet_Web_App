from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.models.load_plan import LoadPlan
from app.models.parcel import Parcel
from app.models.vehicle_capability import VehicleCapability
from app.models.vehicle_type import VehicleTypeCatalog

DOCUMENT_MODELS = [Parcel, VehicleTypeCatalog, VehicleCapability, LoadPlan]

async def init_database(client=None):
    client = client or AsyncIOMotorClient(settings.mongodb_url)
    await init_beanie(database=client[settings.mongodb_database], document_models=DOCUMENT_MODELS)
    return client
