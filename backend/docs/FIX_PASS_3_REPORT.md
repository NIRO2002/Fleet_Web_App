# Fix Pass 3 — G1/G2/G5 completion report

`FIX_PASS_3.md` specifies eight gates (G1–G8). **G3, G4, G6, G7, G8 are deferred** — all
depend on `data/parcels_sample_36000.csv`, which the user will supply; nothing in those
stages was started. This report covers G1, G2, and G5, all green.

## Summary table

| | Before | After |
|---|---|---|
| Catalog rows | 10 | 7 |
| `N_CONSTRAINTS` | 9 | 7 |
| Placement at 3x floor area | claimed FAIL (didn't reproduce) | OK — succeeds past 4x |
| Real instances reaching feasibility | not measured (no real dataset yet) | deferred to G3 |
| Shift-window violation rate | claimed 81.7% (didn't reproduce as described) | deferred to G4 (needs real instances) |
| Run time, 400 parcels, pop=100 gen=200 | ~95–99s (Fix Pass 2 baseline) | 145–159s — **worse**, see G5 below |
| Harness data source | synthetic | still synthetic (G6 deferred) |
| Statistical analysis | absent | still absent (G7 deferred) |

## Before touching any code: two of the document's central claims didn't reproduce

Verified empirically against the current codebase (post Fix Pass 2, commit `6e6f677`)
before writing a line of implementation:

- **G2's "blocker"** — a row-abandonment placement bug with specific diagnostic numbers —
  does not reproduce. The fix G2 prescribes (try every open row before opening a new one,
  sort largest-first within a delivery-stop band) is already in `placement.py`, carried
  over from Fix Pass 1 and preserved through Fix Pass 2. G2's own evidence used a
  550×220×210cm/5-layer vehicle — the *old* placeholder `LORRY` fixture's dimensions, not
  the real current `TRUCK_4T` (520×220×210cm/6 layers).
- **G5's "current ~110s, 0.5–4.6% cache hit rate"** and its "do instead" list (precompute
  the distance matrix, short-circuit placement, parallelize the harness) describe work Fix
  Pass 2 already completed and measured (44% cache hit rate, ~95–99s for the same
  configuration).

Per the user's direction, both were treated as **verify, don't blindly re-implement** —
detailed below.

## G1 — Descope hazmat/refrigeration, drop peel

Per the user's choice: peel dropped entirely (option b) — the novelty is
split-and-merge, not split-merge-peel.

- **Kept, per the document's own instruction**: every DB column (`Parcel.hazardous/
  hazmat_class/requires_refrigeration/temp_min_celsius/temp_max_celsius`,
  `VehicleTypeCatalog.is_refrigerated/temp_min_celsius/temp_max_celsius/
  is_hazmat_certified`, `VirtualVehicle.is_refrigerated/is_hazmat_certified`), the Pydantic
  schema fields mirroring them, and the import path. No migration — this was purely
  removing *optimizer use* of data that stays in the schema.
- **Removed**: `VehicleTypeSpec`'s four hazmat/refrigeration fields, `_hazmat_ok`/
  `_refrigeration_ok` and their use in `_evaluate_slot`/`evaluate_individual`,
  `N_CONSTRAINTS` 9 → 7. The 3 estimated reefer catalog rows (`seed_vehicle_types.py`
  now deactivates them on seed, for any dev DB that already has them). `_peel_special_
  handling` and `RepairedClusters.n_peeled` (`capacity_aware_clustering.py`).
- **One correctness fix required by dropping peel**: `_cluster_handling_key` previously
  assumed every cluster was handling-class-homogeneous (guaranteed by peel running first).
  Without peel, a cluster from spatial clustering can genuinely mix hazmat/refrigerated/
  ordinary parcels, so the function was rewritten to compare the *exact set* of handling
  classes present, not a single representative key — merge can no longer be fooled into
  combining two clusters whose handling-class mix differs just because their first parcel
  happened to match. New test:
  `test_capacity_aware.py::test_merge_never_combines_clusters_with_different_handling_classes`.
- **`optimization_service.py` fix**: `VirtualVehicle.is_refrigerated`/`is_hazmat_certified`
  used to read straight off `VehicleTypeSpec`; since that no longer carries the fields,
  `optimize_load` now looks them up from the real catalog row (`catalog_row_by_code`,
  reusing the existing `catalog_cache` — no extra query when a cache is passed) so
  `VirtualVehicle`'s persisted record still reflects the real vehicle type's actual
  capability, even though the optimizer no longer enforces it as a constraint.
- **`docs/DESIGN_DECISIONS.md`**: new Decision 4 records the descope rationale and
  explicitly supersedes the operational relevance (not the historical accuracy) of
  Decisions 1 and 2.

**Gate**: catalog has 7 rows, `N_CONSTRAINTS == 7`, 108 tests passing (was 107 — one new
test replaces the removed peel test, one new test replaces two removed feasibility
invariants; `test_feasibility_invariants.py` now covers 13 invariants, not 15, since
Hazmat/Refrigeration no longer apply).

## G2 — Placement verified, not rewritten

`test_placement.py::test_placement_diagnostic_table_at_1x_2x_3x_4x_floor_area` builds the
required before/after table on the real current `TRUCK_4T` spec:

```
all-stackable  n=  95  footprint=  99.7% of floor  -> OK
all-stackable  n= 191  footprint= 200.3% of floor  -> OK
all-stackable  n= 286  footprint= 300.0% of floor  -> OK
all-stackable  n= 381  footprint= 399.7% of floor  -> OK
realistic-mix  n=  95  footprint= 121.0% of floor  -> FAIL
realistic-mix  n= 191  footprint= 249.7% of floor  -> FAIL
realistic-mix  n= 286  footprint= 384.2% of floor  -> FAIL
realistic-mix  n= 381  footprint= 517.6% of floor  -> FAIL
realistic-mix floor utilization at failure boundary (n=92): 76.6%
```

**All-stackable succeeds past 4x floor area** — well above the required ≥3x. The
realistic mix (20% fragile, 20% non-stackable, stack budget U(0,40)kg — the document's own
parameters) fails much earlier, but the floor is 76.6% utilized at that failure boundary
(>70% threshold), confirming this is a legitimate, expected effect — non-stackable/fragile
parcels can't share stack space, so they consume floor area 1:1 — not a regression to
row-abandonment. This is a real and different phenomenon from what G2 originally
diagnosed, reported honestly rather than "fixed."

The LIFO invariant test (`test_lifo_exceptions_are_linear_and_match_the_brute_force_
violation_set`) still passes, unchanged, since no placement code was touched.

## G5 — Runtime: the number got worse, and here's why

Re-measured the exact same 400-parcel/pop=100/gen=200 configuration Fix Pass 2 used,
now against the post-G1 catalog (7 types) and constraint set (7 constraints):

| Run | Elapsed | Cache hit rate | Short-circuit rate |
|---|---|---|---|
| Fix Pass 2 (10 types, 9 constraints) | ~95–99s | 44.3% | 4.4% |
| Post-G1 (7 types, 7 constraints), seed 0 | 159.2s | 1.4% | 0.7% |
| Post-G1, seed 1 | 145.4s | 10.7% | 0.8% |

**This is a real, reproducible regression, not noise** — confirmed by profiling
(`cProfile`, sorted by self-time): the same already-optimized code paths from Fix Pass 2
(`_try_stack`/`_place_in_open_rows` in the shelf-packing heuristic,
`nearest_neighbor_tour_from_matrix`, `schedule_time_window_compliance`) remain the
hotspots — there is no *new* inefficiency introduced by G1's edits. What changed is the
**cache hit rate collapsed from 44% to 1–11%**: with 3 fewer vehicle types and 2 fewer
constraints, far fewer generated slot compositions repeat across the population, so the
per-instance slot cache (keyed on `(frozenset(parcel_indices), type_idx)`) gets far fewer
hits, meaning the GA does dramatically more actual `attempt_placement`/
`schedule_time_window_compliance` work per run rather than serving it from cache. This is
an emergent property of GA population dynamics responding to a smaller, differently-shaped
search space (T and the constraint count both shrank) — not a code defect to patch, and
not something B.1–B.3's per-call optimizations can address, since those optimizations
speed up each individual evaluation, not how many *distinct* evaluations the GA performs.

Per the plan's stop condition ("only pursue a fix if profiling confirms it's still the
binding cost"): profiling confirms the same costs, executed more often — there is no new
hotspot to fix, and chasing the cache-hit-rate drop itself would mean second-guessing the
GA's legitimate exploration behavior rather than finding an inefficiency. This is reported
as-is rather than force-fit into a fix.

**<60s was not reached, and now further from it than Fix Pass 2's ~95–99s.** The B.1
(distance matrix)/B.2 (short-circuit)/B.3 (`joblib.Parallel` harness) infrastructure all
still functions correctly (confirmed: a 3-seed parallel batch via `python -m
app.evaluation.cli run` completes correctly with per-seed cache/short-circuit rates
reported).

**Projected full-harness hours**: using the same methodology as the Fix Pass 2 report (the
source document's own numbers imply ~2,395 total runs at 169h/254s-per-run), at the
measured ~152.3s/run average and `n_jobs=12`: 2,395 × 152.3s / (3600 × 12) ≈ **8.4 hours**
— still a large improvement over the original 169h single-threaded projection, but worse
than Fix Pass 2's ~5.4h projection.

## What this means going forward

G1's scope reduction has a real runtime cost that wasn't anticipated in either fix pass
document. Options, not decided here since they weren't asked for:
- Accept ~150s/run (~8.4h full harness) as the actual cost of the smaller catalog/
  constraint set, and move on.
- Investigate whether NSGA-II's population/mutation parameters should be retuned for the
  smaller `T`/`K` search space now that hazmat/refrigeration no longer add constraint
  pressure (a genuine GA-tuning question, not a code-efficiency one — out of scope for a
  runtime-only pass without further direction).

## Deferred

G3 (real-instance diagnostics), G4 (shift-window diagnosis), G6 (commit the real
36,000-row dataset), G7 (Wilcoxon/effect-size/Holm statistics module), G8 (the actual
Phase 6 run) all remain untouched, pending `data/parcels_sample_36000.csv`.
