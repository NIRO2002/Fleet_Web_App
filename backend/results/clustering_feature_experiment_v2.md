# Clustering Feature Experiment v2

## Methodology

Three 400-parcel depot/date instances from 2026-01-05; identical HDBSCAN parameters (min_cluster_size=8, min_samples=4), seed 0, and unchanged capacity-aware repair. B uses midpoint and width with time_weight=5 metres/minute. C/D use the pre-vocabulary-fix urgency mapping so Stage 5A can be evaluated separately.

## Aggregate results

| Configuration | Raw clusters | Noise | Mean distance km | Purity | Time overlap | Splits | Merges | Surviving | Infeasible |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A_location | 5.33 | 0.198 | 1.375 | 0.928 | 0.872 | 7.33 | 47.00 | 33.33 | 0.00 |
| B_location_time | 3.00 | 0.097 | 1.697 | 0.951 | 0.875 | 11.00 | 25.00 | 27.00 | 0.00 |
| C_location_urgency | 9.33 | 0.188 | 1.441 | 0.701 | 0.893 | 4.33 | 43.33 | 33.00 | 0.00 |
| D_location_time_urgency | 8.00 | 0.246 | 1.866 | 0.653 | 0.891 | 3.00 | 59.33 | 32.00 | 0.00 |

## Sensitivity results

The CSV includes location and location+time sensitivity rows at min_cluster_size/min_samples 5/3 and 10/5, with temporal weights 2 and 10 metres/minute.

## Interpretation and recommendation

A versus B is inconclusive: location-only is geographically tighter and needs fewer splits, while time reduces noise, raises neighbour purity, and leaves fewer repaired clusters; temporal overlap improves only marginally. Urgency sharply reduces spatial purity. Location-only remains the conservative default pending broader validation, not a claimed winner.

## Limitations

One delivery date, three depots, seed 0, a bounded parameter sensitivity, and no NSGA-II runs. HDBSCAN is deterministic; seed affects only downstream seeded repair when a split occurs.
