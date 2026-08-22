"""Configuration for the pre-freeze exploratory downstream feature study."""
from app.evaluation.harness import PipelineRunConfig


STUDY_DEPOTS = ("D-CMB-001", "D-CMB-002", "D-CMB-003")
STUDY_DATES = ("2026-01-05", "2026-01-06", "2026-01-07")
STUDY_SEEDS = (0, 1, 2)
STUDY_ARMS = (
    ("location", 5.0),
    ("location_time", 1.0),
    ("location_time", 5.0),
    ("location_time", 20.0),
)


def study_configs() -> list[PipelineRunConfig]:
    """Return the fixed 9-instance x 3-seed x 4-arm design (108 runs)."""
    return [
        PipelineRunConfig(
            depot_id=depot,
            delivery_date=delivery_date,
            method="hdbscan",
            capacity_aware=True,
            seed=seed,
            feature_set=feature_set,
            time_weight=time_weight,
            include_window_width=False,
        )
        for depot in STUDY_DEPOTS
        for delivery_date in STUDY_DATES
        for seed in STUDY_SEEDS
        for feature_set, time_weight in STUDY_ARMS
    ]
