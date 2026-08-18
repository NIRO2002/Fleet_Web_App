# Real dataset

`parcels_sample_36000.csv` — the real parcel dataset the evaluation harness and
integration tests run against (Fix Pass 4 item S5). Supplied by the user 2026-08-18.

## Structure

Verified (`pandas`, this session):

- 36,000 rows, 47 columns.
- 3 depots (`D-CMB-001`, `D-CMB-002`, `D-CMB-003`) × 30 delivery dates = 90
  `(depot_id, delivery_date)` planning instances, **exactly 400 parcels each**.
- No duplicate `parcel_id`s. No nulls in `weight_kg`/`length_cm`/`width_cm`/`height_cm`.
- `hazardous`: 1,384 True / 34,616 False. `hazmat_class` is non-null in exactly those
  1,384 rows where `hazardous` is True, and null everywhere `hazardous` is False — no
  `'none'`-string sentinel (that was an artifact of an older 5,000-row sample; see
  `docs/DESIGN_DECISIONS.md` and the Fix Pass 4 report). `app/tests/test_data_service.py`
  (or wherever S5's real-data verification test lands) asserts this property so a future
  dataset swap can't silently reintroduce it.

## Columns not recognized by the current importer

`ParcelIn`/`data_service.py`'s column mapping recognizes most of this file's columns
directly or via `COLUMN_ALIASES` (`dropoff_lat`→`latitude`, `dropoff_lng`→`longitude`,
etc.). The following are present in the CSV but have no corresponding `ParcelIn` field and
are silently dropped on import (not an error, no warning entry): `order_id`,
`customer_id`, `created_at`, `batch_id`, `dropoff_address`, `dropoff_zone_id`,
`dropoff_postal_code`, `dropoff_location_type`, `floor_number`, `has_elevator`,
`road_access_type`, `actual_shape`, `density_kg_m3`, `top_face_id`, `keep_dry`,
`requires_signature`, `category`, `is_return`, `attempt_number`,
`time_window_flexibility`, `customer_available_probability`, `preferred_time_slot`. None
of this pass's work depends on them; flagged here in case a future pass wants them.

## Instance used for S1's diagnostic and test fixtures

`D-CMB-001` / `2026-01-05`: 400 parcels, 2,974.4 kg, 24.23 m³, median parcel weight 4.78kg,
median `max_stack_weight_kg` (where set) 22.0kg. This is the instance Fix Pass 4's S1
placement diagnosis was verified against.
