from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Fleet Web App - Parcel Optimization Backend"
    app_version: str = "1.0.0"
    database_url: str = "sqlite:///./fleet_web_app.db"

    depot_latitude: float = 6.9271
    depot_longitude: float = 79.8612

    hdbscan_min_cluster_size: int = 8
    hdbscan_min_samples: int = 4

    # Default import region bounds (Colombo). Phase 7 moves these into a
    # nested config model; kept flat for now to unblock Phase 1's importer.
    import_lat_min: float = 6.7
    import_lat_max: float = 7.1
    import_lng_min: float = 79.7
    import_lng_max: float = 80.1

    nsga2_population: int = 80
    nsga2_generations: int = 80

    jwt_secret_key: str = "change-this-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60

    model_dir: str = "artifacts"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()
