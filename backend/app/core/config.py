from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Fleet Web App - Parcel Optimization Backend"
    app_version: str = "1.0.0"
    mongodb_url: str = "mongodb://localhost:27017/"
    mongodb_database: str = "fleet_web_app"

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

    # Safety factor applied to a parcel's imputed (cube-from-volume) side
    # length before dimensional-fit checks (F12) -- an imputed cube is a
    # last-resort guess, not a measurement, so treat it conservatively
    # rather than optimistically.
    imputed_dimension_safety_factor: float = 1.5
    stack_weight_tolerance_kg: float = 0.5
    enforce_weight_order: bool = False

    # Raised from 80/80 now that the assignment problem's search space is
    # real (Phase 3) - the old n_var=1 formulation over 4 fixed options
    # didn't warrant a larger budget, this one does.
    nsga2_population: int = 100
    nsga2_generations: int = 200
    optimization_job_lease_seconds: int = 120
    optimization_worker_poll_seconds: float = 2.0
    # Dev convenience: the API process claims/executes its own queue by
    # default so a lone `uvicorn app.main:app` never leaves jobs stuck
    # QUEUED forever. Set False in deployments that run dedicated
    # `python -m app.workers.optimization_worker` processes instead, to
    # avoid the API competing with them for jobs.
    run_optimization_worker_inprocess: bool = True

    # Clock time the vehicle leaves the depot, used to simulate time-window
    # compliance (Phase 3.2) - starting the simulation at midnight would
    # make every daytime window unreachable.
    depot_departure_time: str = "08:00"

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
