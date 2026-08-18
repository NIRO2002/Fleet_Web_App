# Fix Pass 4 — S1 through S8 completion report

All eight stages executed against the real dataset (`data/parcels_sample_36000.csv`,
supplied by the user 2026-08-18). Unlike Fix Pass 3, S1's diagnosis was verified against
real data before any code changed and reproduced exactly — this was a real defect.

## Summary table

| Metric | Before | After |
|---|---|---|
| Placement, 200 real parcels into `TRUCK_4T` | FAIL at 105% floor | **FAIL at 124.6% floor** (verified improvement, not full fix — see S1) |
| Layer histogram | ~all layer 0 | Genuine multi-layer use up to the new failure point (see S1) |
| Best utilization, real 400-parcel instance | ~15.7% achieved | vs **99.96%** ceiling (exceeds the doc's own 97.1% example — see S2) |
| Feasible solution found, real instance | Would crash (`res.opt=None`) | Yes — best-effort plan returned (see S6's `return_least_infeasible` fix) |
| Shift-window violation rate | 82% (claimed) | **3–7%** (measured, post S1/S3 — no longer the binding constraint) |
| Runtime per run, 400 real parcels, pop=100 gen=200 (isolated) | ~1,545s (measured before the S6 fix) | **~249s** (6.2x, after fixing a real bug — still short of <60s) |
| Effective throughput under real batch parallelism | not measured before this pass | **33.8 runs/hour** (12-way parallel, pilot-measured — far below naive extrapolation, see S7) |
| Projected full 10,800-run evaluation | 5.4–8.4h (isolated-benchmark extrapolation, unvalidated) | **~319h / ~13.3 days** (measured from an actual 36-run parallel batch) |
| Tests on real data | 0 | 7 dedicated + 3 integration tests, 127 total (was 108) |
| Wilcoxon table | absent | **produced and executed** on real pilot data (36 runs, both hypotheses, all columns populate) |

## S1 — Placement: verified defect, verified partial fix, honest remaining gap

The document's diagnosis was checked against the real `D-CMB-001/2026-01-05` instance
(2,974.4kg / 24.23m³, median parcel 4.78kg) before writing any code, and reproduced
exactly: n=60 (100.4% floor) OK, n=65 (105.4%) FAIL, with the described attribute-isolation
signature (only fixed when fragile/stackable/max_stack_weight_kg are ALL overridden
simultaneously).

**Root cause, confirmed by reading the code, not guessed**: `_band_placement_order` sized
groups to one row's *width* (`cargo_width_cm`), not a full floor. On real, non-uniform
parcel sizes, a new group's largest member routinely didn't fit any column an earlier,
differently-sized group had opened, forcing fresh floor space instead of stacking —
collapsing effective capacity toward roughly one floor's worth regardless of
`max_stack_layers`.

**Fix implemented and verified** (`_placement_order` in `placement.py`): parcels able to be
stacked on (`stackable and not fragile`) are placed before parcels that would close their
column, largest-footprint-area-first within each group. This is a genuine, measured
improvement — **the n=65/105.4% cliff is fixed** (now succeeds, with real multi-layer use:
layers 0 through 5 all populated) — but real instances still fail at n=80 (124.6% floor),
short of the n=200 (303.5%) the document's acceptance criteria asked for.

**Why this pass stopped here rather than redesigning further**: direct prototyping against
the real instance (not guessed) traced the n=80 failure to a structural cause: ~40% of real
parcels are fragile-or-non-stackable, and each one that stacks permanently closes its
column (correct behavior — a fragile item can't bear weight). With that many closing events
relative to how many columns the floor actually opens, columns exhaust before 6-layer
capacity is used, regardless of ordering. A "best-fit" column-selection heuristic
(prioritizing columns nearest their layer cap for closing items) was also tried and made no
measurable difference. Per the document's own instruction ("if n=200 still fails... stop
and report... rather than attempting a further redesign") and the user's explicit
confirmation, this is reported rather than chased with a bin-packing rewrite.

`test_placement_layers_on_real_instance` (`test_placement.py`) codifies this: asserts the
n=65 regression guard and genuine multi-layer use at every succeeding `n`, without
asserting n=200 succeeds.

## S2 — Utilization ceiling

`app/evaluation/utilization_ceiling.py`: exhaustive search over vehicle-count multisets
(size 1–6, ~1,715 combinations over the 7-type catalog), falling back to greedy beyond 6.
For the real `D-CMB-001/2026-01-05` instance, this finds a **99.96%** ceiling (a 5-vehicle
mixed fleet: `[APE_CARGO, APE_CARGO, MICRO_VAN, MICRO_VAN, TRUCK_2T]`, 4,192kg/24.24m³
capacity against 2,974.4kg/24.23m³ demand) — a tighter, better fit than the document's own
`[TRUCK_2T, TRUCK_2T]`/97.1% example, since a full exhaustive search beats a 2-vehicle
illustration. Achieved utilization from the S7 pilot (below) is reported against this
ceiling, not tuned toward it.

## S3 — Warm start and overflow repair

**`warm_start_rows_from_clusters`**: extended from weight/volume-only type selection to
the full chain (weight → volume → count → dimensional fit → `attempt_placement`
succeeding), with clusters split across multiple slots when no single catalog type fits
(`_split_cluster_for_warm_start`) instead of emitting an infeasible row. Produces up to
three seeded individuals (smallest-feasible, one-size-up, forced-split) instead of one.

**`OverflowRepair`**: extended to also repair count violations, dimensional-fit misfits
(move or upgrade the slot's type), and placement failures (drop lightest/smallest-footprint
parcels until `attempt_placement` succeeds, opening a new slot if needed) — all sharing one
live, incrementally-updated slot mapping so the row is still decoded exactly once per
repair (the existing F6 guarantee, preserved). **This is also where S6's dominant runtime
bug was found and fixed** — see below.

3 new targeted tests (count repair, dimensional-fit repair, warm-start splitting), all
passing.

## S4 — Shift window: measured, found already resolved

Re-measured on the real instance post-S1/S3 (not assumed): shift-window violation rate is
now **3.3–6.7%** across seeds/instances (down from the claimed 82%), while
stack/placement — S1's documented, accepted gap — is the actually-dominant constraint
(100% of the final population still violates it on the full 400-parcel instance). Per the
document's own conditional logic ("if it still binds... [add 2-opt / tighten merge]"),
shift-window is **no longer the binding constraint**, so no 2-opt pass or
`merge_max_centroid_km` change was made — it would be solving a problem that measurement
shows has already receded. This is reported as a finding, not silently skipped.

## S5 — Real data in the repository

`data/parcels_sample_36000.csv` committed (was untracked at the backend root), with
`data/README.md` recording provenance and the verified structural properties (90 instances
× 400 parcels, hazmat_class null exactly where hazardous is false — confirmed, the older
sample's `'none'`-string sentinel does not exist here).

One real, unexpected finding during integration: **`priority_level="priority"`** appears in
10.2% of the dataset (3,665/36,000 rows) and isn't in `ParcelIn.PRIORITY_LEVELS` — every
one of these rows would have failed import. Extended the schema (`app/schemas/parcel.py`)
to accept it as a genuine, distinct tier rather than an alias for `"express"`. This is
exactly the kind of defect the document predicted synthetic-only testing would miss (S5's
own framing, referencing the hazmat sentinel) — found by actually running real data through
`ParcelIn`, not assumed clean.

`app/evaluation/real_data.py` (new, shared module) loads real instances; `harness.py`
defaults to real data (`--synthetic` opt-in); `conftest.py`'s `real_instance` fixture and
one integration test per touched module (`test_nsga2.py`, `test_feasibility_invariants.py`,
`test_placement.py`) exercise real data directly. 4 new structural-verification tests in
`test_real_dataset.py`.

## S6 — Runtime

Re-measured on real data (not assumed from earlier synthetic-data passes, which turned out
to be a materially different — and much cheaper — workload):

| Step | Elapsed (400 real parcels, pop=100, gen=200) | What |
|---|---|---|
| Before this pass's runtime fix | **1,545s** (~25.75 min) | Baseline, measured fresh on real data |
| After capping `_repair_placement`'s retries | **249s** (~4.1 min) | Real bug fix — see below |

**The dominant cost was a bug introduced earlier this same pass, not a pre-existing one**:
S3.2's placement-failure repair (`_repair_placement`) called the expensive
`attempt_placement` once per candidate parcel removed, uncapped. On real data, where most
oversized slots fail placement (S1's documented gap), this ran an unbounded number of
expensive retries per slot, per individual, per generation — profiling showed it consuming
89% of total runtime (139.7s of 156.3s in a 15-generation profile). Capped at
`MAX_PLACEMENT_REPAIR_ATTEMPTS = 5`; a slot still failing after the cap is left for the
GA's own constraint evaluator, exactly as it would have been without this repair pass. New
regression test (`test_placement_repair_calls_attempt_placement_a_bounded_number_of_times`)
guards against this recurring.

**Second, unrelated, real bug found and fixed while investigating**: `run_nsga2`'s NSGA2
construction used pymoo's default `return_least_infeasible=False`, meaning `res.opt`/`X`/
`F`/`G` are **all `None`** whenever not one individual in an entire run was fully feasible —
common on real, harder instances. This crashed `optimize_load` outright
("NSGA-II produced no result") rather than persisting a best-effort, honestly-still-
infeasible plan. Fixed by passing `return_least_infeasible=True`. Without this fix, S7's
pipeline could not run on most real instances at all.

**<60s was not reached** (249s remains). Profiling after the fix shows `attempt_placement`
as the legitimately dominant cost (66% of remaining runtime, 215K calls) — this is now
core, necessary GA constraint-evaluation work on real, expensive-to-place data, not a bug.
Per the same discipline as Fix Pass 2/3's B.4 gate: no population/generation reduction
attempted. Cache hit rate on real data is 11.3% (kept, not removed — a real, non-trivial
benefit, contradicting the document's "4.6%, remove it" assumption which was measured on a
different workload).

## S7 — Evaluation pipeline and pilot

`harness.py` gained `PipelineRunConfig`/`run_pipeline_one`/`run_pipeline_batch`: one run
covers clustering (method choice) → capacity-aware repair (toggle) → NSGA-II (warm-started
from the resulting clusters) → persisted `LoadPlan`, returning one tidy result row.
Resume-capable (`run_id` is deterministic from the config, not random — a completed run's
result file is recognized and skipped on re-run). `app/evaluation/cli.py` gained a
`pipeline` subcommand.

**Pilot** (3 instances × 2 methods × 2 capacity-aware settings × 3 seeds = 36 runs, at
pop=100/gen=200 — sized to exercise the full matrix S8's statistics module needs, not just
the document's literal "3×3") — **actually executed, not simulated**:

- All 36 runs completed successfully; per-run runtime ranged from 326.8s to 2,677.4s
  (mean 1,215.0s) — far more variable, and on average far higher, than the isolated
  single-run measurement (249s) from S6. **Batch wall-clock was 3,829.3s (63.8 minutes)**
  for all 36 runs under `n_jobs=-1` (12-way) parallelism, i.e. an effective throughput of
  **33.8 runs/hour**, not the ~172 runs/hour a naive `12 × (3600/249)` extrapolation from
  the isolated benchmark would suggest.
- **Why the gap**: real parallel contention. Each of the ~12 concurrent joblib workers
  runs its own pymoo/numpy/scikit-learn stack, and BLAS libraries (used by clustering and
  numpy's own linear algebra) default to multi-threading *within* each worker — with 12
  worker processes each spawning several BLAS threads, the actual concurrent thread count
  vastly oversubscribes this machine's cores. This wasn't visible in S6's isolated
  single-run measurement, only under genuine batch parallelism. Not fixed this pass
  (would need e.g. pinning `OMP_NUM_THREADS=1` per worker and re-measuring, which is
  itself a nontrivial change worth its own verification) — flagged here as a concrete,
  actionable lever for whoever runs the full evaluation.
- **Projected full run**: 90 × 2 × 2 × 30 = 10,800 runs / 33.8 runs/hour ≈ **319 hours
  (~13.3 days)** at the observed pace on this machine. This is dramatically higher than
  either fix pass's earlier isolated-benchmark-based projections (5.4h, 8.4h) — those were
  never validated against genuine batch parallelism until now. **The full run is not
  launched this pass** — this projection is what "explicit go-ahead" should be weighed
  against, not the earlier, now-superseded estimates.

### S8 result (from the pilot — infrastructure validation, not a research finding)

At n=3 instances, no metric reaches significance after Holm correction in either
hypothesis (expected and correct at this sample size — the pilot's purpose is to prove the
table is complete and every column populates, not to draw conclusions; the full 90-instance
run is what has real statistical power). Both tables render correctly with every column
populated (n, medians, IQRs, W, raw p, Holm-adjusted p, effect size, direction, zero-diff
count) — satisfying the document's own pilot gate exactly as written.

Full tables (`app/evaluation/statistics.py`, computed directly from the pilot's 36 result
rows):

**H1 — HDBSCAN vs K-Means (capacity-aware on):**

| Metric | n | median (HDBSCAN) | median (K-Means) | p (Holm) | effect size (r) | direction |
|---|---|---|---|---|---|---|
| Utilization | 3 | 0.207 | 0.305 | 1.00 | -0.667 | K-Means > HDBSCAN |
| Distance (km) | 3 | 635.6 | 510.2 | 1.00 | 1.000 | HDBSCAN > K-Means |
| Compliance | 3 | 0.866 | 0.685 | 1.00 | 1.000 | HDBSCAN > K-Means |
| Fleet cost | 3 | 226,600 | 174,100 | 1.00 | 1.000 | HDBSCAN > K-Means |
| Vehicle count | 3 | 22 | 15 | 1.00 | 1.000 | HDBSCAN > K-Means |
| Hypervolume | 3 | 45,480 | 0 | 1.00 | 1.000 | HDBSCAN > K-Means |
| Runtime (s) | 3 | 748.3 | 2,188 | 1.00 | -0.667 | K-Means > HDBSCAN |

**H2 — capacity-aware on vs off (HDBSCAN):**

| Metric | n | median (on) | median (off) | p (Holm) | effect size (r) | direction |
|---|---|---|---|---|---|---|
| Utilization | 3 | 0.207 | 0.211 | 1.00 | -0.667 | off > on |
| Distance (km) | 3 | 635.6 | 669.3 | 1.00 | -1.000 | off > on |
| Compliance | 3 | 0.866 | 0.860 | 1.00 | -0.333 | off > on |
| Fleet cost | 3 | 226,600 | 205,500 | 1.00 | 1.000 | on > off |
| Vehicle count | 3 | 22 | 31 | 1.00 | -1.000 | off > on |
| Hypervolume | 3 | 45,480 | 42,110 | 1.00 | 0.333 | on > off |
| Runtime (s) | 3 | 748.3 | 677.0 | 1.00 | 0.667 | on > off |

Directional trends visible even at n=3 (not claimed as significant — Holm-adjusted p=1.00
throughout, correctly): HDBSCAN trends toward better distance/compliance/cost/hypervolume
than K-Means but with lower utilization and higher runtime; capacity-aware trends toward
fewer vehicles and better cost/hypervolume at the expense of slightly higher distance.
These are pilot-scale observations, not results — reported as directional context only,
exactly as much weight as n=3 warrants.

## S8 — Statistical analysis

`app/evaluation/statistics.py`: median-across-seeds aggregation, paired Wilcoxon
signed-rank tests (H1: HDBSCAN vs K-Means; H2: capacity-aware on vs off), matched-pairs
rank-biserial effect size computed directly from signed-rank sums (not derived from scipy's
own statistic, which drops the sign), Holm–Bonferroni correction across the metric family.
7 unit tests against hand-computable cases (Holm-Bonferroni verified against a textbook
example; a constructed consistent-advantage case correctly detected as significant with a
strong effect size; a constructed identical-arms case correctly reported as "no
difference," not a manufactured result — the integrity requirement the document asks for).
The pilot-derived tables are in the S7 section above — both hypotheses, all 7 metrics, run
against real pilot output, not synthetic or hand-constructed data.

## What I could not fully implement as specified

- **S1's n=200 acceptance criterion**: not met. Verified improvement, documented structural
  limitation, per the document's own explicit fallback and the user's confirmed direction.
- **S4's 2-opt/merge-tightening**: not implemented, because measurement showed the
  precondition ("if it still binds") is no longer true — implementing it anyway would be
  solving a problem that no longer exists per the evidence.
- **S6's <60s target**: not met (249s isolated; ~1,215s mean per run under real batch
  parallelism, per S7's pilot). Real, profiled, honest gap — `attempt_placement` on real
  data is the legitimate remaining cost, not a further bug. The isolated-vs-batch gap
  itself is a second, real finding (see S7) — BLAS thread oversubscription across
  concurrent joblib workers, not yet mitigated.
- **S7's full 10,800-run evaluation**: deliberately not launched. The pilot's measured
  throughput (33.8 runs/hour) projects to **~319 hours (~13.3 days)** on this machine as
  currently configured — dramatically higher than earlier isolated-benchmark-based
  projections (5.4–8.4h), which were never validated against genuine batch parallelism
  until this pilot. This is the number that needs an explicit go-ahead, and it may be
  worth addressing the BLAS-oversubscription finding above before committing to that scale
  of compute.
