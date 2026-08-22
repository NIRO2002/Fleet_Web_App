"""Small deterministic synthetic inputs for GA-only smoke benchmarks."""
import random
from types import SimpleNamespace


def generate_synthetic_parcels(n=20, seed=0, n_clusters=2, depot_lat=6.9271, depot_lon=79.8612):
    rng = random.Random(seed)
    centres = [(depot_lat + rng.uniform(-.03, .03), depot_lon + rng.uniform(-.03, .03)) for _ in range(n_clusters)]
    rows = []
    for i in range(n):
        lat, lon = centres[i % n_clusters]
        volume = rng.uniform(.01, .05)
        side = (volume * 1_000_000) ** (1 / 3)
        rows.append(SimpleNamespace(
            parcel_id=f"SYN-{i:05d}", depot_id="SYNTHETIC", delivery_date="2026-01-01",
            latitude=lat + rng.uniform(-.002, .002), longitude=lon + rng.uniform(-.002, .002),
            weight_kg=rng.uniform(1, 8), volume_m3=volume, length_cm=side,
            width_cm=side, height_cm=side, time_window_start="09:00", time_window_end="17:00",
            fragile=False, stackable=True, max_stack_weight_kg=0.0,
            loading_orientation_fixed=False, do_not_tilt=False, two_person_lift=False,
            hazardous=False, hazmat_class=None, requires_refrigeration=False,
            priority_level="standard", service_type="standard", cluster_id=None,
        ))
    return rows
