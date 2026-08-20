# Stacking Model and 3D Load View Report

Date: 2026-08-20

## A1-A3: stacking model

- Removed parcel `max_stack_weight_kg` from placement feasibility while
  retaining the imported field for source fidelity.
- Retained the vehicle-level above-floor stack-weight limit.
- Added immediate-support weight ordering with a configurable 0.5 kg
  tolerance, integrated into column selection without globally sorting the
  delivery stream.
- Added explicit support-weight and vehicle-stack-weight invariants.
- Backend regression after A3: 135 passed.

## A4: measurements

Instance: `D-CMB-001 / 2026-01-05`; vehicle: `TRUCK_4T`.

| Measurement | Result |
|---|---:|
| Largest successful ordered prefix, weight rule enabled | 70 |
| Largest successful ordered prefix, rule disabled | 81 |
| Layer histogram at 70 | 0:31, 1:11, 2:11, 3:8, 4:6, 5:3 |
| Parcels above floor | 39 / 70 (55.7%) |
| Weight above floor | 151.339 / 2,500 kg (6.05%) |

The relaxed-capacity monotonic guard passed (81 >= 70). The anticipated
75-parcel figure was not reproduced.

Full HDBSCAN, capacity-aware, seed-0 run (population 100, 200 generations):

| Metric | Saved pilot | New stacking run |
|---|---:|---:|
| Mean utilization | 21.67% | 18.38% |
| Vehicles | 18 | 18 |
| Distance | 607.51 km | 622.12 km |
| Time-window compliance | 79.54% | 79.96% |
| Fleet cost | LKR 175,999 | LKR 203,558 |
| Pareto front / feasible final | 100 / 100 | 100 / 100 |
| Runtime | 437.21 s | 303.62 s |

The headline optimization result became worse, not better. No parameter was
tuned to hide that result.

## B1-B3: export and UI

- Added nested JSON plan retrieval and a CSV assignment export with 404
  handling and CSV parse-back tests.
- Added a Load Plans route with plan lookup, summary, vehicle selection,
  sortable loading table, loading/empty/error states, and CSV download.
- Added Three.js cargo-bay rendering with orbit/zoom, wireframe bay, parcel
  boxes, sequence/weight/layer coloring, load-progress slider, click details,
  and a WebGL fallback.
- Added `three`, `@react-three/fiber`, `@react-three/drei`, and Three.js type
  definitions. The production bundle builds successfully but emits a
  chunk-size warning (1,230.93 kB minified; 339.99 kB gzip).

## B4: real-plan verification

Initial verification exposed a persistence defect: positions were stored but
the selected 90-degree footprint orientation was discarded. The rendered
source dimensions produced one apparent out-of-bounds box and eight apparent
intersections. The actual oriented dimensions are now persisted through
Alembic revision `9c2d147ab611` and used by JSON/CSV exports.

Regenerated real plan: `PLAN-DAF282006F` (26 parcels, 2 vehicles).

- Out-of-bounds oriented boxes: 0
- Pairwise 3D intersections: 0
- JSON endpoint: HTTP 200, 9,683 bytes
- CSV endpoint: HTTP 200, 3,615 bytes

The feasibility invariant suite now performs the same complete oriented-box
bounds and pairwise intersection checks for generated plans.

Visual click-through could not be completed because the in-app browser failed
during its own asset initialization twice, before opening a tab. This is an
environment limitation; no alternate browser automation surface was silently
substituted.

## Final gates

- Backend: 138 passed.
- Frontend: 3 passed.
- Frontend production build: passed (chunk-size warning noted above).
- Frontend lint: passed.
