# Clustering Feature Experiment

## Methodology

Three 400-parcel depot/date instances from 2026-01-05; identical HDBSCAN parameters (min_cluster_size=8, min_samples=4), seed 0, and unchanged capacity-aware repair. Geographic coordinates use a local equirectangular projection in metres; time_weight=5 metres/minute. B2 adds window width. C/D are diagnostic only.

## Aggregate results

| Configuration | Clusters | Noise | Mean distance m | Purity | Time overlap | Splits | Merges | Surviving | Infeasible |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A_location | 24.33 | 0.198 | 729.8 | 0.925 | 0.872 | 9.67 | 8.00 | 26.00 | 0.00 |
| B_location_midpoint | 21.67 | 0.199 | 778.4 | 0.927 | 0.873 | 11.00 | 6.33 | 26.33 | 0.00 |
| B2_location_midpoint_width | 18.67 | 0.097 | 1604.9 | 0.944 | 0.874 | 12.67 | 6.33 | 25.00 | 0.00 |
| C_location_physical | 30.00 | 0.319 | 872.6 | 0.494 | 0.868 | 0.00 | 6.33 | 23.67 | 0.00 |
| D_location_time_physical | 28.00 | 0.396 | 948.8 | 0.592 | 0.869 | 2.33 | 5.67 | 24.67 | 0.00 |

## Sensitivity results

The CSV includes location and location+time sensitivity rows at min_cluster_size/min_samples 5/3 and 10/5, with temporal weights 2 and 10 metres/minute.

## Interpretation and recommendation

Location-only is recommended. Midpoint time produced no meaningful temporal-overlap gain, slightly increased geographic spread, and required more repair splits. Window width reduced noise but more than doubled geographic spread. Physical configurations sharply reduced spatial purity. The recommendation is based on coherence and downstream usefulness, not cluster count.

## Limitations

One delivery date, three depots, seed 0, a bounded parameter sensitivity, and no NSGA-II runs. HDBSCAN is deterministic; seed affects only downstream seeded repair when a split occurs.
