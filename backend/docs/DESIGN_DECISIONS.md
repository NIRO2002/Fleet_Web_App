# Design decisions

Decisions made where the source data or spec was ambiguous enough that a
different reader could reasonably have chosen differently. Recorded here so
an examiner (or future maintainer) can see the reasoning, not just the
result.

## Placement (Fix Pass 4, item S1)

### Decision 8 — clustering seeds one whole-instance assignment problem

Fix Pass 5 re-audited the evaluation call chain after a report suggested
that each cluster was optimized independently. That report did not match
the implementation: `run_pipeline_one` passes all 400 parcels to one
`optimize_load` call, while repaired clusters are used only to construct
warm-start rows. `LoadPlan.n_vehicles` counts used slots from that single
selected solution. The slot budget is also dynamic, not fixed at 12; for
`D-CMB-001/2026-01-05` it was 29 because warm-start cluster count is a
lower bound on the available search slots.

At seed 0 before consolidation repair, the final feasible population/front
grew from 20/7 at 25 generations to 100/77 at 100 and 100/100 at 200. The
front therefore did not collapse to one point. The real defect was that
overflow repair only spread parcels outward: at 200 generations the
selected solution used all 29 slots, including two one-parcel loads
(min/median/max 1/12/35). Fleet fixed cost was correctly charged once per
used slot. Repair now makes one bounded attempt to empty a least-loaded
slot into already feasible loads. At 25 generations this reduced the
selected plan from 29 to 23 used slots while increasing the feasible final
population from 20 to 100; the front contained 22 distinct points.

### Decision 9 — the K-Means capacity-aware arm is a measured pass-through

The capacity-aware flag is wired identically for HDBSCAN and K-Means. In
both complete 36-run pilots, however, every K-Means repair audit was
`n_split=0, n_merged=0`; therefore its on/off metrics were byte-identical.
K-Means chooses its cluster count from total volume divided by mean catalog
vehicle volume, so those clusters already satisfy the current aggregate
split and proximity/time merge rules. This is correct no-op behavior, not
evidence that the flag failed to reach repair. Evaluation rows now emit an
explicit enabled/disabled audit so this distinction remains visible.

This finding describes the pre-I5 aggregate-only predicate and is
superseded by Decision 10 below; it is retained because it explains why
the earlier pilot arms were identical.

### Decision 10 — split includes parcel count and physical placement

Across the three pilot instances, two methods and three seeds, 282 clusters
were inspected before changing the split predicate. None exceeded any
vehicle by aggregate weight/volume/dimension, but 36 passed those aggregate
checks and failed the production placement routine. The largest cluster
held 378 parcels; the closest observed ratios to `TRUCK_4T` were 61.5% by
weight, 91.1% by volume and 28.8% by longest dimension. Aggregate-only
splitting therefore moved placement infeasibility downstream into NSGA-II.

**Decision**: a cluster fits only when at least one active catalog vehicle
also accepts its parcel count and passes `attempt_placement`. Every split
check records demand and largest-vehicle limits in the audit. The default
recursion cap is 10 rather than 6 because a balanced split of a 400-parcel
instance can require nine levels. Afterward, seed-0 HDBSCAN produced 4/7/4
splits across the three depots; K-Means produced 15/21/14. No depth cap was
hit and every repaired cluster passed the same placement-aware predicate.
The contribution is consequently split-and-merge in measured practice,
not merge-only.

### Decision 7 — zero stack headroom is intentional for non-stackable parcels

The dataset generator is not included in this repository, so its exact random
drawing rule cannot be audited from source. The committed 36,000-row dataset
was therefore checked directly. Exactly 15,000 parcels (41.67%) are
non-stackable and those same 15,000 rows, with no exceptions, have
`max_stack_weight_kg == 0`. No stackable parcel has zero headroom; their
minimum is 2.57 kg and median is 22.33 kg. All 4,805 fragile parcels are
non-stackable. The zero mass is consequently a sentinel for a property that
is meaningless on non-stackable parcels, not evidence of zero support being
drawn for stackable cartons.

**Decision**: retain the dataset unchanged. On `D-CMB-001/2026-01-05`, the
production placement routine accepts the first 74 real parcels in a
`TRUCK_4T` and fails from 75 through 100 (with two earlier non-monotonic
failures at 62 and 63 caused by the heuristic reordering the changed set).
The capacity-only 99.96% figure therefore remains a theoretical aggregate
bound and is not physically reachable evidence. Results must additionally
report `compute_placement_aware_ceiling`, which runs every claimed load
through the production placement routine. Its result is labelled an
attainable reference, not a mathematically proven global upper bound.

### Decision 5 — the placement fix is reported as partial, not papered over

Real-data verification (`data/parcels_sample_36000.csv`) confirmed the placement
heuristic collapsed to roughly one floor's worth of capacity regardless of
`max_stack_layers`, on real (non-uniform) parcel sizes. The fix implemented
(`_placement_order` in `app/optimization/placement.py`: stack-eligible
parcels placed before column-closing ones, largest-footprint-area-first)
is a verified, measured improvement — the specific n=65/105.4%-of-floor
cliff the diagnosis reported is fixed — but real 400-parcel instances still
fail placement at n=80 (124.6% of floor), short of the theoretical 6-layer
capacity.

**Decision**: report this honestly as a partial fix with numbers, rather
than either (a) claiming full success, or (b) pursuing a bin-packing
redesign this pass. Direct prototyping against the real instance (not
guessed) traced the remaining gap to a structural cause: ~40% of real
parcels are fragile-or-non-stackable, and each one that stacks permanently
closes its column (correct behavior). With that many closing events
relative to how many columns the floor opens, columns exhaust before
6-layer capacity is used, regardless of placement order. A first-fit vs.
best-fit column-selection change was tried and made no measurable
difference, confirming the bottleneck is structural, not an easy
algorithmic tweak. See `docs/FIX_PASS_4_REPORT.md` for the full diagnostic
trail.

### Decision 6 — the utilization ceiling is computed exhaustively, not assumed

The source document's own worked example for the real instance
(`[TRUCK_2T, TRUCK_2T]`, 97.1% utilization) was recomputed independently
(`app/evaluation/utilization_ceiling.py`) rather than trusted, per this
project's established practice of verifying claimed diagnostics against
real data before building on them. An exhaustive search over fleet sizes
1-6 finds a tighter fit: `[APE_CARGO, APE_CARGO, MICRO_VAN, MICRO_VAN,
TRUCK_2T]` at 99.96% utilization. The document's example wasn't wrong, just
not exhaustive — reported as the corrected figure, not silently substituted
without explanation.

## Scope (Fix Pass 3, item G1)

### Decision 4 — hazmat and refrigeration are descoped from the optimizer; peel is dropped

Neither hazardous goods nor cold chain appears in any Specific Objective or
Functional Requirement of the submitted proposal. This is commercial
last-mile parcel delivery. Both were introduced by earlier fix passes and
are withdrawn here.

**Decision**: `VehicleTypeSpec` (the optimizer's per-run snapshot) no
longer carries `is_refrigerated`/`temp_min_celsius`/`temp_max_celsius`/
`is_hazmat_certified`, and NSGA-II's constraint set drops the two hazmat/
refrigeration constraints (`N_CONSTRAINTS` 9 -> 7). The three estimated
reefer catalog rows (`VAN_MED_REEFER`, `TRUCK_2T_REEFER`,
`TRUCK_4T_REEFER` -- Decision 1 below) are removed from seeding entirely;
the catalog returns to the 7 field-data rows. Capacity-aware clustering's
"peel" operation, whose entire purpose was pre-grouping hazmat/refrigerated
parcels before splitting, is removed -- the operation is **split-and-merge**,
not split-merge-peel, and that is the honest description of the novelty
going forward.

**What stays, deliberately**: every underlying data column
(`Parcel.hazardous/hazmat_class/requires_refrigeration/temp_min_celsius/
temp_max_celsius`, `VehicleTypeCatalog.is_refrigerated/temp_min_celsius/
temp_max_celsius/is_hazmat_certified`, `VirtualVehicle.is_refrigerated/
is_hazmat_certified`) and the import path that populates them. The data is
in the dataset and costs nothing to keep; "the data supports it, we scoped
it out" is a stronger answer than not having considered it at all.
`capacity_aware_clustering.py`'s merge step still keeps clusters with
different handling classes apart (`_cluster_handling_key`) -- not because
of peel (which no longer exists), but because merging a hazardous cluster
into a non-hazardous one would misrepresent the resulting cluster's
contents, which is a reason independent of whether NSGA-II enforces
eligibility downstream.

This supersedes the operational relevance (not the historical accuracy) of
Decision 1's reefer-row derivation and Decision 2's "gives peel genuine
work to do" remark below -- both decisions are kept for the record, since
the reasoning was sound for the scope that existed at the time.

## Vehicle catalog (Fix Pass 2, item A)

### Decision 1 — refrigeration is a separate catalog row, not a boolean flag

**Superseded by Decision 4 above (Fix Pass 3 G1)**: the three reefer rows
described here were removed from seeding when refrigeration was descoped
from the optimizer. Kept for the record.

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

**Superseded by Decision 4 above (Fix Pass 3 G1)**: `is_hazmat_certified`
is no longer read by the optimizer, and the "peel" step this decision
referenced no longer exists. Kept for the record.

The source data is `Yes (With Permit)` for `TRUCK_2T`/`TRUCK_4T`, `Limited`
for `VAN_MED`, `No` for the rest. `is_hazmat_certified` is a boolean; there
is no modellable middle state for "Limited".

**Decision** (as it stood in Fix Pass 2): `is_hazmat_certified=True` only
for `TRUCK_2T` and `TRUCK_4T`. `VAN_MED`'s "Limited" is read conservatively
as `False`, since treating it as `True` would let the optimizer route
hazardous parcels onto a vehicle class that may not legally carry them
under a "limited" permit. The `is_hazmat_certified` column itself is
unchanged by Fix Pass 3 -- only the optimizer's use of it is gone.

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
