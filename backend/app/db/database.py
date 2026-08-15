from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base

from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args)
Base = declarative_base()
