# Design decisions

Decisions made where the source data or spec was ambiguous enough that a
different reader could reasonably have chosen differently. Recorded here so
an examiner (or future maintainer) can see the reasoning, not just the
result.

## Remediation stages 4C–6 (2026-08-21)

### Clustering features and degeneracy

Production HDBSCAN uses projected location only. In the corrected controlled
experiment, location-only (A) was stable across all three 400-parcel
instances. Location plus midpoint and width (B) collapsed on
`D-CMB-001/2026-01-05`: its largest cluster contained 382/400 parcels
(95.5%, normalized size entropy 0.144), and mean intra-cluster distance rose
from 1.655 km to 2.753 km. Its 0.976 neighbour purity is not evidence of
better cohesion because purity approaches one as cluster granularity
collapses. Purity is therefore compared only when cluster counts are within
approximately 2x. Urgency variants also reduced geographic purity. SO2 is
accordingly stated as: **identify stable geographic delivery-density groups
per depot/date**. Urgency remains on complete Parcel records for downstream
priority, scheduling, assignment and reporting; it is not a similarity
feature.

### Time windows are both a soft objective and a coarse repair guard

Parcel delivery compliance is deliberately NSGA-II soft objective f3: hard
per-parcel enforcement could make real instances have no feasible solution
and would hide the trade-off the Pareto front is intended to expose. Repair
does use an independently switchable coarse temporal split predicate. Its
lower bound is `parcel_count * 4 service minutes + one approximate diameter
traverse / vehicle speed`, compared with the span from earliest opening to
latest closing. It is not a tour estimate. The diameter uses a deterministic
two-sweep farthest-point O(n) lower bound; this avoids the former O(n²)
matrix inside every vehicle/pair check.

### Noise policy

Raw HDBSCAN cluster count excludes noise. A noise parcel is reassigned only
when its nearest real-cluster centroid is within 0.75 km. Original-noise
confidence is sentinel `-1.0` and `Parcel.is_noise` remains true. Unassignable
points stay `-1` until repair, where each becomes a marked singleton eligible
for normal feasibility-aware merging. Final repaired IDs are normalized to
non-negative integers; raw and post-noise counts are reported separately.

### Priority vocabulary

Accepted values include the real dataset's `standard`, `express`, and
`priority`, plus schema-supported `next_day` and `same_day`. Unknown values
raise validation errors. The diagnostic urgency score `priority=2.5` between
`express=2.0` and `same_day=3.0` is an explicit, unverified ordinal
assumption: the dataset generator is unavailable, and `next_day`/`same_day`
do not occur in the measured file. It must not be presented as source-backed
semantics.

### Authoritative depots and fleet ceilings

Depot coordinates and hours come from `depots_table4_sample_10.csv`, Table 4:
D-CMB-001 `(6.927079,79.861244)`, D-CMB-002
`(6.864908,79.899678)`, and D-CMB-003 `(6.851320,79.865576)`. The former
global origin was correct only for D-CMB-001 and invalidated historical
distance results for the other two depots. Unknown IDs now fail; there is no
global fallback. Request coordinates are permitted only as an explicit
latitude/longitude pair for ad-hoc API runs. Depot closing time tightens each
catalog vehicle's return deadline, and selected plans are rejected above the
depot's 95/70/58 vehicle ceiling.

### Reproducibility and runtime

Plan UUIDs and timestamps remain operational metadata and are excluded from
semantic determinism comparisons. With the same seed/config and one worker,
the gate compares cluster/repair assignments, selected parcel/vehicle
assignments, objective vectors and constraint vectors byte-for-byte. A real
400-parcel clustering+repair run measured 3.69 seconds after incremental
merge caching (about 11.1 hours for 10,800 repair stages). Historical full
NSGA-II runs measured 292–311 seconds, projecting roughly 36–39 serial days;
the full evaluation must not launch without parallel-capacity planning.

## Placement (Fix Pass 4, item S1)

### Decision 8 - clustering seeds one whole-instance assignment problem

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

### Decision 9 - the K-Means capacity-aware arm is a measured pass-through

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

### Decision 10 - split includes parcel count and physical placement

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

### Decision 7 - zero stack headroom is intentional for non-stackable parcels

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
report `compute_utilization_greedy_reference`, which runs every claimed load
through the production placement routine. Its result is labelled an
attainable reference, not a mathematically proven global upper bound.

### Decision 5 - the placement fix is reported as partial, not papered over

Real-data verification (`data/parcels_sample_36000.csv`) confirmed the placement
heuristic collapsed to roughly one floor's worth of capacity regardless of
`max_stack_layers`, on real (non-uniform) parcel sizes. The fix implemented
(`_placement_order` in `app/optimization/placement.py`: stack-eligible
parcels placed before column-closing ones, largest-footprint-area-first)
is a verified, measured improvement - the specific n=65/105.4%-of-floor
cliff the diagnosis reported is fixed - but real 400-parcel instances still
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

### Decision 6 - the utilization ceiling is computed exhaustively, not assumed

The source document's own worked example for the real instance
(`[TRUCK_2T, TRUCK_2T]`, 97.1% utilization) was recomputed independently
(`app/evaluation/utilization_ceiling.py`) rather than trusted, per this
project's established practice of verifying claimed diagnostics against
real data before building on them. An exhaustive search over fleet sizes
1-6 finds a tighter fit: `[APE_CARGO, APE_CARGO, MICRO_VAN, MICRO_VAN,
TRUCK_2T]` at 99.96% utilization. The document's example wasn't wrong, just
not exhaustive - reported as the corrected figure, not silently substituted
without explanation.

## Scope (Fix Pass 3, item G1)

### Decision 4 - hazmat and refrigeration are descoped from the optimizer; peel is dropped

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

### Decision 1 - refrigeration is a separate catalog row, not a boolean flag

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

### Decision 2 - hazmat certification: "Limited" reads as not certified

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

### Decision 3 - `max_parcels` is a derived estimate, not source data

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
## Stacking model change (2026-08-20)

Parcel-level `max_stack_weight_kg` is retained as imported source data but is
no longer treated as a load-bearing capacity constraint. The source field's
meaning is not sufficiently reliable for cumulative support calculations,
and applying it that way rejected physically plausible stacks. The vehicle
catalog's `vehicle_max_stack_weight_kg` remains a hard limit.

Placement now enforces a directly auditable rule: a parcel placed above
another parcel may weigh at most 0.5 kg more than its immediate support.
The rule is applied while selecting an open column; parcel delivery/LIFO
order is not globally weight-sorted. Fragile and non-stackable parcels may
be placed as the final parcel in a compatible column but cannot support a
subsequent parcel.

On the ordered prefixes of the real `D-CMB-001 / 2026-01-05` instance in a
`TRUCK_4T`, the largest successful prefix was 70 with weight ordering and 81
with the rule disabled. Thus the requested monotonic guard passed, although
the expected 75-parcel estimate did not: the measured values are 70 and 81.
At 70 parcels the layer histogram was `0:31, 1:11, 2:11, 3:8, 4:6, 5:3`;
39/70 (55.7%) were above the floor and their combined 151.339 kg used only
6.05% of the vehicle's 2,500 kg above-floor allowance.

For the pre-launch configuration freeze, weight ordering is therefore an
optional ablation and defaults to **off**. The three recorded capacities are:
old per-parcel-limit model 70 (historical measurement), current immediate-
support ordering 70, and ordering disabled 81. The pre-launch prompt's claim
that the current ordered model fits 61 was re-measured and proved wrong on
this checkout. Across the 36,000-row dataset, 41.67% (not the prompt's 25%)
of `max_stack_weight_kg` values are exactly zero and 42.11% are below 5 kg;
median parcel weight is 4.99 kg and median recorded stack limit is 11.86 kg.
Those values were not grounded in observed logistics operations, supporting
removal of the per-parcel constraint. Heavy-bottom ordering remains
physically principled, but its measured 70-versus-81 density cost makes it an
explicit option rather than the main experimental model. This default was
frozen here before the final experiment, not selected after observing final
results.

The full HDBSCAN/capacity-aware/seed-0 run (population 100, generations 200)
did not improve the optimization headline: relative to the saved pilot,
utilization changed 21.67% -> 18.38%, vehicles stayed at 18, distance changed
607.51 -> 622.12 km, cost LKR 175,999 -> 203,558, and runtime changed
437.21 -> 303.62 s. This is reported as measured rather than tuning the new
rule to force a utilization gain; NSGA-II stochastic search and the changed
feasible region can select a different trade-off solution.
## Pre-launch R7 stop decision (2026-08-20)

The 36-run validation pilot triggered the mandatory no-launch rule: one
K-Means/capacity-off run had a single-point infeasible front (0 feasible
final individuals, maximum violation 70.080), making that arm's
infeasibility rate 11.1%; two capacity-on arms also regressed slightly in
median utilization versus `launch_pilot`. The full evaluation was therefore
not launched and no parameter was tuned post hoc. See
`docs/PRE_LAUNCH_REPORT.md` for the complete evidence and projection.
# HDBSCAN delivery-similarity features (2026-08-21)

HDBSCAN runs independently per `(depot_id, delivery_date)` and uses a local
equirectangular projection in metres. This is physically meaningful over the
small study areas and avoids independently z-scoring latitude and longitude.
Time is encoded as window midpoint (optionally width), with an explicit
`time_weight` in metres per minute; the tested default was 5 m/min.

The controlled three-depot experiment supported **location-only** as the
production default. Adding midpoint time gave essentially no temporal-overlap
gain, slightly worsened geographic spread, and caused more repair splits.
Adding width doubled geographic spread despite lower noise. Diagnostic
physical configurations sharply reduced spatial purity. Therefore weight,
volume, dimensions, fragility and stackability are excluded from production
HDBSCAN similarity while remaining on complete Parcel objects for unchanged
capacity-aware repair, NSGA-II and placement. The feature set stays
configurable so this decision can be re-evaluated on datasets with stronger
time-window separation.

## cluster_id is scoped, not globally unique -- `label_offset` removed (2026-08-24)

HDBSCAN labels restart at 0 for every `(depot_id, delivery_date)` planning
instance (`app/services/clustering_service.py`'s `cluster()` always fits
fresh per instance). `Parcel.cluster_id` is a bare int with no instance
scope baked in, so the same `cluster_id` value legitimately exists across
many unrelated instances -- it was never meant to be a global identifier.

The multi-instance CSV/dataset training path (`api/v1/parcels.py`'s
`dataset_id` branch) previously worked around this by accumulating a
`label_offset` across instances so cluster IDs looked dataset-wide unique;
the single depot+date training path never did the same. This inconsistency
was symptomatic of the real bug: `POST /optimization/run`'s `cluster_id`
branch resolved parcels with a global `{"cluster_id": N}` query
(`api/v1/optimization.py`), so for most clusters it silently pulled in
parcels from every instance that happened to reuse that label, tripping the
"parcels must share exactly one delivery_date" guard.

The fix is to resolve `cluster_id` together with `(depot_id, delivery_date)`
everywhere it's used (see `OptimizationRequest`'s new required-when-
`cluster_id`-is-set `depot_id`/`delivery_date` fields, and the compound
`(depot_id, delivery_date, cluster_id)` index on `Parcel`), not to keep
papering over the missing scope with an offset. `label_offset` is removed
entirely from `train_hdbscan`, the persisted joblib bundle, and
`predict_cluster`; per-instance labels starting at 0 are the natural,
correct output of clustering once every consumer resolves them with their
instance scope.
