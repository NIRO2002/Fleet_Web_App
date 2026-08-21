# Clustering Feature Experiment v2

## Methodology

Three 400-parcel depot/date instances from 2026-01-05; identical HDBSCAN parameters (min_cluster_size=8, min_samples=4), seed 0, and unchanged capacity-aware repair. B and D explicitly set include_window_width=True and use midpoint plus width with time_weight=5 metres/minute. C/D use the pre-vocabulary-fix urgency mapping so Stage 5A can be evaluated separately. A run is flagged degenerate when its largest non-noise cluster exceeds 60% of the instance.

Spatial purity is only comparable at similar cluster granularity; it is not interpreted when cluster counts differ by more than approximately 2x.

## Per-instance results

| Instance | Configuration | Raw clusters | Noise | Max share | Entropy | Degenerate | Mean km | Purity | Overlap | Surviving |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| D-CMB-001_2026-01-05 | A_location | 6 | 0.253 | 0.247 | 0.887 | False | 1.655 | 0.914 | 0.870 | 39 |
| D-CMB-001_2026-01-05 | B_location_time | 2 | 0.025 | 0.955 | 0.144 | True | 2.753 | 0.976 | 0.871 | 21 |
| D-CMB-001_2026-01-05 | C_location_urgency | 10 | 0.242 | 0.182 | 0.923 | False | 1.821 | 0.630 | 0.898 | 37 |
| D-CMB-001_2026-01-05 | D_location_time_urgency | 8 | 0.242 | 0.230 | 0.905 | False | 1.992 | 0.628 | 0.902 | 34 |
| D-CMB-002_2026-01-05 | A_location | 5 | 0.117 | 0.275 | 0.950 | False | 1.042 | 0.939 | 0.878 | 34 |
| D-CMB-002_2026-01-05 | B_location_time | 4 | 0.113 | 0.275 | 0.990 | False | 1.115 | 0.953 | 0.875 | 34 |
| D-CMB-002_2026-01-05 | C_location_urgency | 10 | 0.165 | 0.207 | 0.921 | False | 1.858 | 0.584 | 0.915 | 37 |
| D-CMB-002_2026-01-05 | D_location_time_urgency | 9 | 0.188 | 0.203 | 0.909 | False | 1.971 | 0.603 | 0.912 | 38 |
| D-CMB-003_2026-01-05 | A_location | 5 | 0.223 | 0.255 | 0.913 | False | 1.427 | 0.930 | 0.870 | 27 |
| D-CMB-003_2026-01-05 | B_location_time | 3 | 0.152 | 0.460 | 0.898 | False | 1.222 | 0.923 | 0.880 | 26 |
| D-CMB-003_2026-01-05 | C_location_urgency | 9 | 0.200 | 0.170 | 0.934 | False | 1.695 | 0.608 | 0.882 | 29 |
| D-CMB-003_2026-01-05 | D_location_time_urgency | 6 | 0.217 | 0.163 | 0.990 | False | 1.913 | 0.611 | 0.847 | 25 |

## Aggregate results

| Configuration | Raw clusters | Noise | Max share | Entropy | Mean distance km | Purity | Time overlap | Splits | Merges | Surviving | Infeasible |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A_location | 5.33 | 0.198 | 0.259 | 0.917 | 1.375 | 0.928 | 0.872 | 7.33 | 47.00 | 33.33 | 0.00 |
| B_location_time | 3.00 | 0.097 | 0.563 | 0.677 | 1.697 | 0.951 | 0.875 | 11.00 | 25.00 | 27.00 | 0.00 |
| C_location_urgency | 9.67 | 0.203 | 0.187 | 0.926 | 1.792 | 0.607 | 0.898 | 2.33 | 47.33 | 34.33 | 0.00 |
| D_location_time_urgency | 7.67 | 0.216 | 0.198 | 0.935 | 1.959 | 0.614 | 0.887 | 1.67 | 56.67 | 32.33 | 0.00 |

## Sensitivity results

The CSV includes location and location+time sensitivity rows at min_cluster_size/min_samples 5/3 and 10/5, with temporal weights 2 and 10 metres/minute.

## Corrected interpretation

A is stable across all three instances. B is unstable: on D-CMB-001 its largest cluster contains 382/400 parcels (95.5%), which is a degenerate collapse. B's high spatial purity there is an artifact of coarse granularity and is not compared with A's purity. The honest geographic signal is mean intra-cluster distance, which rises from 1.655 km (A) to 2.753 km (B) on that instance. Urgency configurations also reduce geographic purity at comparable granularity. The evidence supports A (location only) as the stable default; this conclusion is based on collapse resistance and geographic cohesion, not fewer clusters.

## Limitations

One delivery date, three depots, seed 0, a bounded parameter sensitivity, and no NSGA-II runs. HDBSCAN is deterministic; seed affects only downstream seeded repair when a split occurs.
