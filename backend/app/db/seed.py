from app.db.database import Base, engine
from app.models.parcel import Parcel
from app.models.virtual_vehicle import VirtualVehicle

def init_db():
    Base.metadata.create_all(bind=engine)
    return True

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
