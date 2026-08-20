# Pre-Launch Pass Report

Date: 2026-08-20

## Decision

**NO-LAUNCH after R7.** R8 and R9 were not executed. The R7 stop rule fired
because one Pareto front collapsed to one infeasible solution, the K-Means
capacity-off arm had 11.1% infeasible runs, and two capacity-on arms regressed
in median utilization relative to `launch_pilot`.

## R1 — stacking configuration

- `enforce_weight_order` is default-off and is threaded through settings,
  optimizer configuration, placement feasibility/repair, persistence,
  evaluation CLI, result rows, greedy reference, and manifest.
- `TRUCK_4T`, `D-CMB-001 / 2026-01-05`: historical per-parcel model 70;
  immediate-support ordering 70 (the prompt's 61 was not reproduced);
  ordering disabled 81.
- Dataset measurement: 41.67% of stack-limit values are zero (not 25%),
  42.11% are below 5 kg, median parcel weight is 4.99 kg, and median source
  stack limit is 11.86 kg.
- Gate: 140 tests passed.

## R2 — reproducibility

- Threaded the run seed into recursive split K-Means; no hardcoded
  `random_state=0` remains in application code.
- Same-process pymoo runs produced byte-identical `res.X`, `res.F`, and
  `res.G` for the same seed.
- HDBSCAN noise IDs are sorted before centroid construction; cluster/slot
  dictionaries derive from stable parcel and numeric slot order. No numeric
  decision fed directly from unordered set iteration was found.
- Every results directory has a manifest. Old directories are explicitly
  marked reconstructed and unknown historical fields are null, not invented.
  Contrary to the prompt, `launch_pilot` already had a readable SHA
  (`9430420...`); it lacked the complete dataset/config/catalog contract.
- New manifests include dataset filename/SHA-256, redacted config and CLI
  snapshot, seeds, commit/dirty state, tracked library versions, catalog
  digest, and weight-order setting.
- Gate: 142 tests passed.

## R3 — determinism gate

Configuration: `D-CMB-001 / 2026-01-05`, HDBSCAN, capacity-aware on,
seed 0, population 100, generations 200, weight ordering off.

The prompt's literal command would queue 180 runs because this CLI defaults
to all 90 instances and both capacity settings. The test used explicit
`--instances` and `--capacity-aware on` to implement its stated single-
configuration intent.

| Execution | Runtime (s) | Non-runtime numeric differences |
|---|---:|---:|
| serial A | 311.115 | baseline |
| serial B | 292.699 | 0 |
| production path A (`n_jobs=-1`) | 299.474 | 0 |
| production path B (`n_jobs=-1`) | 291.798 | 0 |

All four manifests recorded commit `4456c98...`. **Determinism: GO.** Runtime
is intentionally excluded from equality because it is wall-clock measurement,
not an optimizer output.

## R4–R6

- Every new result row has `feasible`, `feasible_individuals_final`, and
  `max_constraint_violation`. Least-infeasible rows remain available for
  diagnosis but are excluded from hypothesis tests and counted per arm.
- Placement-bound terminology was removed. The attainable heuristic is now
  `compute_utilization_greedy_reference`; only the capacity value is called a
  ceiling.
- Real data fails closed unless `--synthetic` is explicitly requested.
  Verified: 36,000 rows, 90 instances, 400 parcels each, 3 depots × 30 dates.
- Gate after R6: 146 tests passed.

## R7 — 36-run validation pilot

Instances: 2026-01-05 from each of D-CMB-001, D-CMB-002, and D-CMB-003.
Population 100, generations 200, seeds 0–2, weight ordering off.

`n_jobs=-1` launched 12 workers and failed after 1,126.6 seconds with Windows
resource error 1450 after persisting 6/36 rows. Resume was verified: those six
rows were skipped and the remaining 30 completed at stable `n_jobs=6` in
3,973.5 seconds.

Medians across nine runs per arm:

| Method | Capacity aware | Vehicles | Util. | Achieved / greedy | Distance km | Compliance | Cost LKR | Front | Feasible final | Infeasible | Split / merged | Runtime s | Batch runs/h |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| HDBSCAN | Off | 15 | 23.07% | 98.88% | 619.2 | 76.50% | 175,970 | 95 | 100 | 0/9 | 0 / 0 | 654.0 | 27.18 shared |
| HDBSCAN | On | 16 | 23.04% | 92.86% | 607.2 | 78.32% | 179,367 | 93 | 100 | 0/9 | 4 / 7 | 597.4 | 27.18 shared |
| K-Means | Off | 11 | 20.16% | 89.87% | 417.7 | 75.68% | 173,077 | 100 | 100 | **1/9** | 0 / 0 | 851.6 | 27.18 shared |
| K-Means | On | 10 | 18.56% | 77.41% | 386.7 | 77.50% | 185,963 | 84 | 100 | 0/9 | 14 / 3 | 827.9 | 27.18 shared |

The runs/hour value is a batch measurement and cannot honestly be attributed
to one arm because arms ran concurrently. Overall throughput including the
failed 12-worker attempt was 25.41 runs/hour.

### Required answers

1. **No, the claimed 22 → 17 vehicle improvement was not reproducible as a
   paired improvement.** For HDBSCAN capacity-on versus `launch_pilot`, 2/9
   runs improved, 2/9 tied, and 5/9 used more vehicles. New counts ranged
   from 10 to 19, with median 16.
2. **No.** Eleven arm×instance groups stayed well above one (minimum 50 or
   more), but D-CMB-002/K-Means/cap-off/seed-1 collapsed to a front of one.
3. **The K-Means ablation affected every instance.** Utilization, distance,
   compliance, and cost differed for all three seeds in all depots. Vehicle
   count did not differ for every seed, so it is not uniformly different on
   that one metric.
4. **Yes.** Split fired in all three depots for both capacity-aware methods.
5. **The compliance change was instance/seed-specific, not consistent.**
   Paired HDBSCAN/cap-on changes had mixed signs; median change was +0.50pp
   for D-CMB-001, -2.69pp for D-CMB-002, and -0.42pp for D-CMB-003.
6. **One run was infeasible:** D-CMB-002/K-Means/cap-off/seed-1, with zero
   feasible final individuals and maximum constraint violation 70.080.

### Stop evidence

- Front-collapse gate: failed (one front of size 1).
- Infeasibility gate: failed (K-Means cap-off 11.1%, above approximately 10%).
- Utilization-regression gate: failed versus `launch_pilot` medians for
  HDBSCAN cap-on (-0.11pp) and K-Means cap-on (-0.63pp).
- Final R7 regression: 146 tests passed.

## Projection and checklist (no launch)

Stable six-worker throughput was 27.18 runs/hour. A 10,800-run evaluation
projects to 397.35 hours or **16.56 days**. Even 15 seeds projects to about
8.28 days. The prompt's under-five-day launch envelope is not met.

| Pre-launch item | Result |
|---|---|
| Determinism at serial and production path | PASS |
| Resume verified by interruption/failure | PASS |
| Manifest with real SHA; clean tree; no `--allow-dirty` | PASS |
| BLAS thread pinning in workers | PASS |
| `feasible` in every new row | PASS |
| One tidy row per run | PASS (36/36) |
| Disk space | PASS (47.99 GiB free; pilot files 44,965 bytes) |
| R7 quality gates | **FAIL — NO LAUNCH** |

R8 launch and R9 statistics/freeze were not started because doing so would
violate the pass's explicit stop rule. No optimizer or clustering parameter
was tuned in response to these results.
