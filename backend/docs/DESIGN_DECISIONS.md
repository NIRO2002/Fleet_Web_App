# Design decisions

Decisions made where the source data or spec was ambiguous enough that a
different reader could reasonably have chosen differently. Recorded here so
an examiner (or future maintainer) can see the reasoning, not just the
result.

## Vehicle catalog (Fix Pass 2, item A)

### Decision 1 — refrigeration is a separate catalog row, not a boolean flag

The source data marks refrigeration as "Optional (Chiller)" for `VAN_MED`
and "Optional (Reefer Box)" for `TRUCK_2T`/`TRUCK_4T`. `is_refrigerated` on
`VehicleTypeCatalog` is a plain boolean, and neither value is correct for an
"optional" capability: marking the base row `True` makes refrigeration free
everywhere (undercounting cost), while marking it `False` makes every
refrigerated parcel in the dataset unplannable on those vehicle classes
(overconstraining feasibility).

**Decision**: the seven field-data rows are all `is_refrigerated=False`.
Three additional rows -- `VAN_MED_REEFER`, `TRUCK_2T_REEFER`,
`TRUCK_4T_REEFER` -- are added as `is_refrigerated=True` variants of the
corresponding base type, `source="estimated_variant"`.

**Derivation of the reefer variants' figures** (no field data exists for
these -- estimated, not measured):
- **Capacity**: reduced ~10% by volume from the base type, to account for
  chiller-unit/insulation intrusion into the cargo bay. Weight capacity
  reduced proportionally.
  - `VAN_MED` 6.00 m3 -> `VAN_MED_REEFER` 5.40 m3 (1100kg -> 1000kg)
  - `TRUCK_2T` 12.48 m3 -> `TRUCK_2T_REEFER` 11.20 m3 (2500kg -> 2300kg)
  - `TRUCK_4T` 24.02 m3 -> `TRUCK_4T_REEFER` 21.60 m3 (4500kg -> 4200kg)
- **Cost**: `fixed_cost` +50% (chiller unit capital/maintenance cost),
  `cost_per_km` +15% (fuel cost of running the compressor in transit).
- **Temperature range**: -18C to 8C on all three, spanning frozen and
  chilled requirements, since the source data doesn't distinguish them.

If any Phase 6 instance turns out infeasible specifically because of these
estimated reefer capacities, that should be reported as-is rather than
silently loosened -- the numbers are flagged estimates precisely so a
downstream reader can revise them with visibility into what changed.

### Decision 2 — hazmat certification: "Limited" reads as not certified

The source data is `Yes (With Permit)` for `TRUCK_2T`/`TRUCK_4T`, `Limited`
for `VAN_MED`, `No` for the rest. `is_hazmat_certified` is a boolean; there
is no modellable middle state for "Limited".

**Decision**: `is_hazmat_certified=True` only for `TRUCK_2T` and
`TRUCK_4T`. `VAN_MED`'s "Limited" is read conservatively as `False`, since
treating it as `True` would let the optimizer route hazardous parcels onto
a vehicle class that may not legally carry them under a "limited" permit.
This makes the two largest trucks mandatory for the dataset's 144 hazardous
parcels, which is realistic and gives the capacity-aware clustering "peel"
step genuine work to do.

### Decision 3 — `max_parcels` is a derived estimate, not source data

The source table gives weight and volume capacity but no parcel-count cap.
`max_parcels` is derived per vehicle type as a rough count scaled from
`capacity_m3`, using a declining parcels-per-m3 ratio as vehicles get
larger (smaller vehicles tend to carry smaller, more numerous parcels
relative to their volume). It is not expected to bind before the
weight/volume/dimensional constraints do -- see
`app/db/seed_vehicle_types.py` for the exact figures.

### `cost_per_trip_reference` is provenance-only

The source data's per-trip quotes (`cost_per_trip - fixed_cost) /
cost_per_km` back out to a coherent "typical trip length" series (4.0-26.3
km across the seven field-data types), so it's stored on the catalog row for
provenance/auditing but is never read by the objective function --
`fixed_cost + cost_per_km * distance` already fully prices a trip, and
summing in the bundled quote as well would double-count.
