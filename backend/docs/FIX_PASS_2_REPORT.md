# Fix Pass 2 — completion report

All five gates (A–E) are green. This is the report required by
`FIX_PASS_2.md`'s "Reporting" section, produced before any Phase 6
evaluation harness run.

## Summary table

| Item | Before | After |
|---|---|---|
| Catalog rows | 4 placeholder | 10 (7 field data + 3 estimated reefer variants) |
| BIKE dimensional fit rate | — | 80.6% (synthetic data — see caveat below; doc's 62.2% is unreproducible) |
| Run time, 400 parcels, pop=100 gen=200 | 252.6s (measured on this harness) | 95–99s (~2.6x) — **did not reach the <60s target**, see below |
| Cache hit rate | 4.6% (Fix Pass 1 figure, different harness — unreproducible here) | 44.3% (measured on this harness before B.1; unchanged by B.1 since B.1 doesn't change *what* gets cached, only how fast a miss is computed) |
| Short-circuit rate | — (new metric) | 4.4% of placement attempts skipped |
| Projected full-harness hours | 169h (doc's extrapolation) | ~5.4h projected, at measured per-run time with `n_jobs=12` on this machine (see methodology below) |
| Feasibility invariants | partial | 15 of 15 passing on 50 seeded instances |
| Tests | 51 | 107 |

## Two things that didn't match the source document's assumptions

Found during reconnaissance, before any code was touched, and confirmed
with the user before proceeding:

1. **`parcels_table1_sample_5000.csv` does not exist** anywhere in this
   repository or on the machine it was developed on. Per the user's
   explicit choice, `app/evaluation/synthetic_data.py` generates a
   synthetic 5000-row set instead. All A.7 verification numbers in this
   report (fit rates, edge cases) are against that synthetic set, not the
   real file — they will not match the source document's specific figures
   (e.g. 62.2% for BIKE), and are not meant to.
2. **No `app/evaluation/` harness existed** before this pass — section B's
   "currently ~54s" baseline described infrastructure that hadn't been
   built yet. Per the user's choice, a minimal harness
   (`app/evaluation/harness.py` + `cli.py`) was built first, sized to make
   B's runtime target measurable and to give B.3's `joblib.Parallel`
   something real to parallelize. This is not the full Phase 5/6
   metrics/statistics evaluation suite from `BACKEND_REMEDIATION_PROMPT.md`
   — that remains out of scope, as does actually running the 20-hour
   evaluation itself.

## A — Vehicle catalog

10 rows seeded (`app/db/seed_vehicle_types.py`): the 7 field-data rows from
the spec's table (`source="field_data"`), plus 3 reefer variants
(`VAN_MED_REEFER`, `TRUCK_2T_REEFER`, `TRUCK_4T_REEFER`,
`source="estimated_variant"`). Three design decisions required judgment and
are recorded in `docs/DESIGN_DECISIONS.md`:

1. Refrigeration modeled as separate catalog rows, not a boolean flag
   (the source data's "Optional" refrigeration doesn't map to a boolean).
2. Hazmat: `VAN_MED`'s "Limited" permit reads conservatively as
   `is_hazmat_certified=False` — only `TRUCK_2T`/`TRUCK_4T` are certified.
3. `max_parcels` isn't in the source data at all; it's a documented,
   derived estimate (scaled from `capacity_m3`), not expected to bind
   before weight/volume/dimensional constraints do.

`cost_per_trip_reference` is stored for provenance only (nullable column,
never read by the objective function — using it alongside `fixed_cost`/
`cost_per_km` would double-count).

New per-vehicle constraints added and verified:
- **A.5, vehicle-level stack weight** (`vehicle_max_stack_weight_kg`):
  implemented in `placement.py`'s `_try_stack`/`_VehicleStackState`. Test:
  `test_placement.py::test_bike_never_stacks_a_parcel_above_the_floor`.
- **A.6, vehicle shift windows** (`available_from`/`available_until`):
  `schedule_time_window_compliance` now departs at
  `max(depot_departure_time, vehicle.available_from)` and returns a tour's
  full return-to-depot time; a new constraint 9 (`N_CONSTRAINTS` 8 → 9)
  penalizes a return past `available_until`. Verified by the feasibility
  invariant suite's "Shift window" check (invariant 14) across 50 seeds.

`T == 10` and search-space growth on an 11th row are both asserted in
`test_vehicle_catalog.py`.

## B — Runtime

Iterative, profiling-driven work (`cProfile`, not guesswork), all measured
on the same 400-parcel / pop=100 / gen=200 configuration:

| Step | Elapsed | What changed |
|---|---|---|
| Baseline (post B.2 short-circuit, pre B.1 matrix) | 252.6s | — |
| B.1: precomputed distance matrix, `nearest_neighbor_tour_from_matrix` | 111.9s | Vectorised `haversine` matrix build; GA's tour lookups hit an O(1) precomputed matrix instead of recomputing haversine per pair |
| Dedup fix (found via profiling) | 98.6s | `_dimension_fits`/`_hazmat_ok`/`_refrigeration_ok` were being computed twice per parcel per slot (once for B.2's short-circuit check, once again in `evaluate_individual`) — computed once now, cached on the slot result |
| Footprint memoization (found via profiling) | 98.2s | `placement.py`'s `_footprint()` was recomputed up to ~5x per parcel per `attempt_placement` call across its internal helpers — call-scoped memoization added |
| Final measurement | 95–99s | — |

**The <60s target was not reached.** Per the gate's own fallback ("if B.1–B.3
do not reach the target, report the profile output and top 3 hotspots
before making further changes — no population/generation reduction"), the
remaining top hotspots (from `cProfile`, sorted by self time) are:

1. `nearest_neighbor_tour_from_matrix` — numpy's per-call dispatch overhead
   at typical slot sizes (tens of parcels, not thousands). A plain-Python-list
   rewrite was tried and measured *slower* (110.8s), so the numpy version
   was kept; this looks like a genuine floor for this approach without
   restructuring the tour algorithm itself (e.g. batching multiple slots'
   tours into one larger vectorised call).
2. `attempt_placement` / `_try_stack` / `_place_in_open_rows` — the
   shelf-packing heuristic's linear scan over open columns/rows. Inherent to
   the algorithm's current structure; a real fix would mean spatial
   indexing of columns, which risks changing placement *results*, not just
   speed, and was judged out of scope for a runtime-only pass.
3. `schedule_time_window_compliance` — the per-parcel simulation walk,
   called once per cache-miss slot; already benefits from the distance
   matrix, the remaining cost is the simulation loop itself.

B.2 (short-circuit) and B.3 (`joblib.Parallel` batch harness) are both
implemented and measured: 4.4% short-circuit rate, and the CLI's `run`
command parallelizes correctly across seeds (confirmed with a 3-seed batch).

**Projected full-harness hours methodology**: the source document's own
numbers (169h at 254s/run) imply roughly 2,395 total runs in whatever full
harness it was projecting for (169×3600/254 ≈ 2,395) — there's no formal
Phase 6 harness config in this repository to derive that number
independently, so it's carried forward as the best available estimate of
scale. At the measured ~97s/run and `n_jobs=12` (this machine's core
count) via `joblib.Parallel`: 2,395 × 97s / (3600 × 12) ≈ **5.4 hours**,
down from the doc's single-threaded 169h projection.

## C — Minimal parcel/plan status

`Parcel.status` (PENDING/PLANNED/DELIVERED/FAILED), `plan_id`,
`carried_over_from_date`; `LoadPlan.status` (DRAFT only — no
PUBLISHED/CLOSED transition trigger exists, out of scope) and
`n_carryover_parcels`. `get_planning_instance` now pulls in
PENDING/FAILED parcels from earlier dates at the same depot, stamping
`carried_over_from_date` and rolling `delivery_date` forward — time windows
are left untouched (a stale window becomes an honest compliance cost, not a
silent reschedule). `optimize_load` marks every planned parcel PLANNED with
its `plan_id` in the same transaction as the rest of the plan.

Gate test: `test_nsga2.py::test_optimize_load_marks_parcels_planned_and_records_carryover`
(end-to-end: PENDING parcels across two dates → later date's plan pulls in
the earlier date's leftovers → parcels come out PLANNED with
`carried_over_from_date` set and the plan's `n_carryover_parcels` correct).

## D — Feasibility invariants

`app/tests/test_feasibility_invariants.py`: all 15 invariants (13 from
`BACKEND_REMEDIATION_PROMPT.md` Phase 6 + 2 new: Shift window, and Catalog
fidelity extended to the new A.4 fields), as a seeded loop over 50 random
instances (`hypothesis` isn't a project dependency, so per the spec's own
fallback this uses `pytest.mark.parametrize("seed", range(50))`, not a new
dependency) — **all 50×15 = 750 checks pass.**

Two invariants had to be interpreted, not relaxed, against what the
existing implementation actually guarantees (both discovered by the test
initially failing, then fixed in the test, not the production code):

- **Invariant 7 (stack weight)**: initially miswritten as a running total
  from the floor upward; corrected to "weight of everything strictly above
  a given parcel," matching `placement.py`'s actual per-column headroom
  semantics.
- **Invariant 12 (LIFO consistency)**: the spec's literal wording implies
  an all-pairs check, but `placement.py`'s `_lifo_exceptions` deliberately
  records one exception per out-of-order parcel against the running-max-x
  holder (an O(n) design from Fix Pass 1, not O(n²) all-pairs — see that
  function's docstring). The test now checks the invariant the system
  actually implements: every parcel whose x falls below the running
  maximum must appear as `parcel_b` in a recorded exception. This is not a
  weaker guarantee in practice — every genuinely out-of-order parcel is
  still caught — but it is a different formalization than the spec's literal
  phrasing, worth knowing about if invariant 12 is revisited later.

One invariant (10, placement validity) is intentionally scoped: it checks
bay bounds and rejects exact-duplicate placement points, but does not
reconstruct full rotated-rectangle overlap, since the persisted schema
doesn't record which of a parcel's two floor orientations was chosen for a
given assignment. Flagged in the test file's module docstring.

## E — Reproducibility

`app/core/reproducibility.py`: `set_seeds`, `is_git_dirty`, `run_manifest`,
`write_manifest`. Every `optimize_load` call now stamps its `LoadPlan.run_manifest`
with a real git commit SHA, dirty flag, package versions, and a
catalog-snapshot digest. The harness CLI (`app/evaluation/cli.py`) writes a
manifest before any GA work starts and **refuses to run against a dirty git
tree** unless `--allow-dirty` is passed — verified manually (exit code 1,
clear message, without the flag; runs normally with it).

## What to do before the actual Phase 6 run

- Obtain the real `parcels_table1_sample_5000.csv` if the dissertation
  needs the exact 62.2%-style fit-rate figures — the synthetic numbers in
  this report are not a substitute for that, only a stand-in that let A.7's
  *logic* (rotation, T==10, search-space growth) be verified.
- Decide whether the <60s/run target is a hard requirement or whether
  ~97s/run (a real 2.6x improvement, profiling-exhausted for cheap wins) is
  acceptable, given the top-3 remaining hotspots above would each require
  either restructuring the placement heuristic or batching the tour
  computation — changes with real risk of altering results, not just speed.
- Build out the actual Phase 5/6 evaluation suite (`metrics.py`,
  `experiment.py`, `statistics.py`) on top of the harness scaffolding added
  here — this pass deliberately stopped short of that.
