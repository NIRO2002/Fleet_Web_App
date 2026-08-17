"""Seeded synthetic parcel generation.

`parcels_table1_sample_5000.csv` (referenced by Fix Pass 2 item A.7) does not
exist anywhere in this checkout or on the machine it was developed on --
verified by search before this module was written. Per the user's explicit
choice, this generates a synthetic 5000-row set instead and reports whatever
fit-rates it actually produces, rather than the source document's
figures (which are tied to the missing real file and cannot be reproduced
here). See docs/DESIGN_DECISIONS.md.

This is the single generator behind three consumers that would otherwise
each reinvent it: `app/tests/conftest.py`'s `parcel_factory` fixture (thin
wrapper, kept there for pytest ergonomics), item A.7's verification, the
runtime harness (item B), and the feasibility-invariant tests (item D) --
the latter needs edge cases (hazardous/refrigerated/fragile/non-stackable
parcels) injected so those invariants are non-vacuous.
"""
import random


def parcel_payload(
    parcel_id: str,
    lat: float,
    lon: float,
    weight: float,
    volume: float,
    tw_start: str,
    tw_end: str,
    fragile: bool,
    depot_id: str,
    delivery_date: str,
    *,
    length_cm: float | None = None,
    width_cm: float | None = None,
    height_cm: float | None = None,
    stackable: bool = True,
    max_stack_weight_kg: float = 0.0,
    loading_orientation_fixed: bool = False,
    hazardous: bool = False,
    hazmat_class: str | None = None,
    requires_refrigeration: bool = False,
    temp_min_celsius: float | None = None,
    temp_max_celsius: float | None = None,
    two_person_lift: bool = False,
) -> dict:
    return {
        "parcel_id": parcel_id,
        "depot_id": depot_id,
        "delivery_date": delivery_date,
        "latitude": lat,
        "longitude": lon,
        "weight_kg": weight,
        "volume_m3": volume,
        "time_window_start": tw_start,
        "time_window_end": tw_end,
        "fragile": fragile,
        "length_cm": length_cm,
        "width_cm": width_cm,
        "height_cm": height_cm,
        "stackable": stackable,
        "max_stack_weight_kg": max_stack_weight_kg,
        "loading_orientation_fixed": loading_orientation_fixed,
        "hazardous": hazardous,
        "hazmat_class": hazmat_class,
        "requires_refrigeration": requires_refrigeration,
        "temp_min_celsius": temp_min_celsius,
        "temp_max_celsius": temp_max_celsius,
        "two_person_lift": two_person_lift,
    }


def generate_synthetic_parcels(
    n: int = 20,
    seed: int = 0,
    n_clusters: int = 2,
    depot_lat: float = 6.9271,
    depot_lon: float = 79.8612,
    depot_id: str = "DEPOT-1",
    delivery_date: str = "2026-08-20",
    *,
    with_dimensions: bool = False,
    hazmat_fraction: float = 0.0,
    refrigeration_fraction: float = 0.0,
    non_stackable_fraction: float = 0.0,
    two_person_lift_fraction: float = 0.0,
    max_weight_kg: float = 8.0,
    include_edge_cases: bool = False,
) -> list[dict]:
    """Deterministic synthetic parcel generator: `n` parcels jittered around
    `n_clusters` geographic centers near the depot (same `seed` always yields
    the same set). `with_dimensions=False` (the default) reproduces the
    original `conftest.py` behaviour exactly (weight/volume only, no
    length/width/height, no handling-constraint edge cases) for callers that
    don't need the richer fields.

    `include_edge_cases=True` appends fixed rows exercising known extremes
    (heaviest, largest-volume, longest-side) at the *end* of the returned
    list, past index `n` -- used by A.7's dimensional-fit verification so
    those checks aren't purely a function of the random draw.
    """
    rng = random.Random(seed)
    centers = [
        (depot_lat + rng.uniform(-0.03, 0.03), depot_lon + rng.uniform(-0.03, 0.03))
        for _ in range(n_clusters)
    ]
    payloads = []
    for i in range(n):
        clat, clon = centers[i % n_clusters]
        lat = clat + rng.uniform(-0.002, 0.002)
        lon = clon + rng.uniform(-0.002, 0.002)
        weight = round(rng.uniform(1.0, max_weight_kg), 2)
        volume = round(rng.uniform(0.01, 0.05), 3)
        start_h = rng.choice([9, 10, 11])
        end_h = start_h + 3

        kwargs = {}
        if with_dimensions:
            # Cube-ish dimensions consistent with volume_m3, in cm, with
            # enough spread that BIKE's tiny 45x45x45 bay excludes a
            # meaningful fraction (A.7).
            side = round((volume * 1_000_000) ** (1 / 3) * rng.uniform(0.8, 1.6), 1)
            kwargs["length_cm"] = side
            kwargs["width_cm"] = round(side * rng.uniform(0.6, 1.0), 1)
            kwargs["height_cm"] = round(side * rng.uniform(0.6, 1.0), 1)
        if hazmat_fraction and rng.random() < hazmat_fraction:
            kwargs["hazardous"] = True
            kwargs["hazmat_class"] = rng.choice(["3", "8", "9"])
        if refrigeration_fraction and rng.random() < refrigeration_fraction:
            kwargs["requires_refrigeration"] = True
            kwargs["temp_min_celsius"] = -18.0
            kwargs["temp_max_celsius"] = 8.0
        if non_stackable_fraction and rng.random() < non_stackable_fraction:
            kwargs["stackable"] = False
        if two_person_lift_fraction and rng.random() < two_person_lift_fraction:
            kwargs["two_person_lift"] = True

        payloads.append(
            parcel_payload(
                f"P{i:05d}",
                lat,
                lon,
                weight,
                volume,
                f"{start_h:02d}:00",
                f"{end_h:02d}:00",
                rng.random() < 0.15,
                depot_id,
                delivery_date,
                **kwargs,
            )
        )

    if include_edge_cases:
        clat, clon = centers[0]
        payloads.append(
            parcel_payload(
                "EDGE-MAX-WEIGHT", clat, clon, 80.0, 0.09, "09:00", "17:00", False, depot_id, delivery_date,
                length_cm=45.0 if with_dimensions else None,
                width_cm=40.0 if with_dimensions else None,
                height_cm=50.0 if with_dimensions else None,
            )
        )
        payloads.append(
            parcel_payload(
                "EDGE-MAX-VOLUME", clat, clon, 20.0, 0.663, "09:00", "17:00", False, depot_id, delivery_date,
                length_cm=95.0 if with_dimensions else None,
                width_cm=90.0 if with_dimensions else None,
                height_cm=78.0 if with_dimensions else None,
            )
        )
        payloads.append(
            parcel_payload(
                "EDGE-MAX-SIDE", clat, clon, 15.0, 0.30, "09:00", "17:00", False, depot_id, delivery_date,
                length_cm=115.0 if with_dimensions else None,
                width_cm=45.0 if with_dimensions else None,
                height_cm=58.0 if with_dimensions else None,
            )
        )

    return payloads
