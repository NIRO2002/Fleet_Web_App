# Fix Pass 5 — utilization-gap investigation

I1–I5 were executed in order against the real 36,000-parcel dataset. No
optimizer parameter was tuned to improve an outcome.

## Requested before/after instance

`D-CMB-001 / 2026-01-05`, HDBSCAN, capacity-aware, seed 0,
population 100, generations 200.

| Metric | Pilot claim | After |
|---|---:|---:|
| Mean utilization | 19.9% | 22.96% |
| Vehicles used | 22 | 17 |
| Placement-aware attainable reference | not reported | 22.44% |
| Achieved / placement reference | — | 102.34% |
| Capacity-only theoretical ceiling | 100.0% | 99.96% |
| Pareto front size | 1 | 100 |
| Feasible individuals at final generation | unknown | 100 / 100 |
| Parcels per slot (min/median/max) | unknown | 16 / 21 / 44 |
| K-Means ablation differs? | No | Yes |
| `n_split` / `n_merged` | 0 / 48 (pilot aggregate) | 4 / 8 (this run) |
| Distance | 630 km | 589.2 km |
| Compliance | 85.5% | 75.1% |
| Fleet cost | LKR 224,618 | LKR 163,361 |
| Runtime | 419 s (old six-worker mean) | 477.8 s (this run) |

`compute_utilization_greedy_reference` is deliberately an attainable greedy
reference, not a proven upper bound. Achieving 102.34% of it means NSGA-II
found a better feasible packing than that conservative reference; it does
not mean a physical ceiling was violated.

## I1 — architecture audit

The premise was wrong for the current code. The harness calls
`optimize_load` once with all 400 parcels. Repaired clusters only seed the
whole-instance GA. Vehicle count is the number of used slots in that one
selected solution, not a sum of cluster-level plans. `K` is dynamic and is
at least the warm-cluster count; it was 29 in the diagnostic, not a hard
12. No artificial per-cluster path was added.

## I2 — front and slot saturation

Before consolidation, generation 25/100/200 measurements were:

| Generations | Feasible final | Front size | Used/K | Slot min/median/max |
|---:|---:|---:|---:|---:|
| 25 | 20/100 | 7 | 29/29 | 1/14/33 |
| 100 | 100/100 | 77 | 29/29 | 1/13/32 |
| 200 | 100/100 | 100 | 29/29 | 1/12/35 |

Every front objective vector was distinct. Duplicate elimination was not
collapsing the front, and the run was not falling back to one
least-infeasible point. Fleet fixed cost was correctly charged once per
used vehicle. The real defect was outward-only overflow repair. A bounded
rollback-safe step now attempts to close one least-loaded slot while
rechecking all constraints. At 25 generations it produced 100 feasible
individuals, a 22-point front and 23 used slots.

## I3 — ceiling reporting

New rows emit capacity-only theoretical maximum, placement-aware attainable
reference, and achieved/reference ratios separately. The legacy ceiling
key remains temporarily for old result compatibility. Statistical output
uses achieved/placement-reference as the headline and labels capacity-only
as theoretical.

## I4 — K-Means ablation

Before I5, both full pilot directories proved repair was correctly wired
but was a genuine K-Means pass-through (`n_split=0`, `n_merged=0`). I5
superseded that behavior by adding placement-aware splitting, after which
K-Means split on every measured instance. Enabled and disabled rows now
always carry explicit audits, and a wiring regression test asserts they
differ when repair fires.

## I5 — split predicate

Across 18 clustering runs (three instances × two methods × three seeds),
282 clusters were inspected. Aggregate oversize count was zero, but 36
aggregate-fit clusters failed physical placement. Maximum observed cluster
size was 378; maximum ratios to the largest vehicle were 61.5% weight,
91.1% volume and 28.8% longest dimension. Split now checks count and the
production placement routine and records its inputs. With the corrected
depth bound, all repaired clusters fit and no cap was hit. Seed-0 outcomes:

| Depot | HDBSCAN split/merge | K-Means split/merge |
|---|---:|---:|
| D-CMB-001 | 4 / 8 | 15 / 5 |
| D-CMB-002 | 7 / 10 | 21 / 1 |
| D-CMB-003 | 4 / 2 | 14 / 3 |

The contribution is split-and-merge in measured practice.

## Revised 36-run pilot

| Arm | Mean utilization | Vehicles | Distance km | Compliance | Cost LKR | Runtime s |
|---|---:|---:|---:|---:|---:|---:|
| HDBSCAN, repair on | 22.55% | 15.67 | 584.2 | 77.66% | 185,956 | 478.8 |
| HDBSCAN, repair off | 22.10% | 16.78 | 613.5 | 78.98% | 194,874 | 435.3 |
| K-Means, repair on | 20.35% | 11.56 | 460.0 | 76.71% | 180,759 | 538.8 |
| K-Means, repair off | 25.41% | 10.33 | 454.6 | 73.78% | 162,150 | 617.6 |

K-Means without repair wins utilization, vehicle count, distance and cost
in this pilot; repair improves its compliance. This mixed/negative result
is reported unchanged.

Batch wall time was 3,338.8 seconds at six workers: 38.82 runs/hour. Mean
per-run runtime was 517.6 seconds (range 347.3–857.6). The projected full
10,800-run evaluation is 278.2 hours (11.6 days), so it was not launched.
