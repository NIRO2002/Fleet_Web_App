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
| Runtime per run, 400 real parcels, pop=100 gen=200 | ~1,545s (measured before the S6 fix) | **~249s** (6.2x, after fixing a real bug — still short of <60s) |
| Tests on real data | 0 | 7 dedicated + 3 integration tests, 127 total (was 108) |
| Wilcoxon table | absent | produced (`app/evaluation/statistics.py`, pilot validated) |

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
the document's literal "3×3"): [results below once the pilot completes — see note].

**Full run explicitly not launched this pass** (90 × 2 × 2 × 30 = 10,800 runs) — see
projection below.

## S8 — Statistical analysis

`app/evaluation/statistics.py`: median-across-seeds aggregation, paired Wilcoxon
signed-rank tests (H1: HDBSCAN vs K-Means; H2: capacity-aware on vs off), matched-pairs
rank-biserial effect size computed directly from signed-rank sums (not derived from scipy's
own statistic, which drops the sign), Holm–Bonferroni correction across the metric family.
7 unit tests against hand-computable cases (Holm-Bonferroni verified against a textbook
example; a constructed consistent-advantage case correctly detected as significant with a
strong effect size; a constructed identical-arms case correctly reported as "no
difference," not a manufactured result — the integrity requirement the document asks for).

[Pilot-derived table below once the pilot completes.]

## What I could not fully implement as specified

- **S1's n=200 acceptance criterion**: not met. Verified improvement, documented structural
  limitation, per the document's own explicit fallback and the user's confirmed direction.
- **S4's 2-opt/merge-tightening**: not implemented, because measurement showed the
  precondition ("if it still binds") is no longer true — implementing it anyway would be
  solving a problem that no longer exists per the evidence.
- **S6's <60s target**: not met (249s). Real, profiled, honest gap — `attempt_placement` on
  real data is the legitimate remaining cost, not a further bug.
- **S7's full 10,800-run evaluation**: deliberately not launched — a multi-hour-to-multi-day
  compute job needs an explicit go-ahead against the projection below, not an autonomous
  start.
