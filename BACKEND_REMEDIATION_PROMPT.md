# Backend Remediation Specification — Parcel Consolidation & Load Optimization

**How to use this file:** open Claude Code in the `Fleet_Web_App/backend` directory and paste
the whole document as your first message, or save it in the repo and say
"Read BACKEND_REMEDIATION_PROMPT.md and execute Phase 0 through Phase 8 in order."

---

## 0. Role and context

You are working on the backend of an undergraduate dissertation research project
(SLIIT, R26-IT-001, student IT22255792). The research component is **parcel
consolidation and load optimization**: given a set of parcels for one depot on one
day, produce a load plan that assigns every parcel to a virtual vehicle, optimizing
several conflicting objectives simultaneously.

The project must defend a specific research claim: *spatial clustering (HDBSCAN)
combined with capacity-aware cluster repair and NSGA-II multi-objective assignment
produces better load plans than a K-Means + single-objective baseline.* Every change
you make must serve that claim or the code that evidences it.

**Hard scope boundary — do not cross it.** Route optimization, real fleet assignment,
driver scheduling, and live vehicle tracking belong to a teammate's separate module.
This backend ends at the load plan. Files named `auth.py`, `vehicles.py`,
`maintenance.py`, `predictions.py`, `demand.py`, `deliveries.py`, `routes.py`,
`trips.py`, `alerts.py`, `reports.py` are deliberate placeholders owned by that
teammate — leave their public shape alone except where Phase 8 explicitly says otherwise.
Nearest-neighbour distance in this codebase is a *cost estimate for the optimizer*,
not a route. Do not upgrade it into a routing engine.

**Research integrity requirement.** You are building the machinery to run a fair
comparison. You are not building machinery to make HDBSCAN win. Do not tune the
baseline down, do not filter instances, do not select seeds. If the comparison comes
out unfavourable, that is a valid result and it gets reported as-is.

---

## 1. Current state — the defects you are fixing

A code review found the following. Read this list carefully; several fixes depend on
understanding *why* the current design fails, not just what to change.

### 1.1 CRITICAL — NSGA-II is decorative and must be redesigned

In `app/services/optimization_service.py`:

- `minimize(problem, NSGA2(...), ...)` is called and **its return value is discarded.**
  There is no `res =`. Nothing NSGA-II computes reaches the API.
- The result actually returned is produced by a loop that ranks the four vehicle types
  by a hand-tuned weighted sum:
  `0.45*util_weight + 0.20*util_volume + 0.20*compliance + 0.15/(1+distance)`.
  This is a scalarised single-objective heuristic — exactly the approach the research
  gap says is inadequate.
- The field named `pareto_solutions` is not a Pareto front. It is every feasible vehicle
  type sorted by that scalar score.
- **The decision variable is the wrong thing.** `n_var=1`, an integer over four vehicle
  types, with `metrics()` called on a *fixed* parcel list. So distance and compliance do
  not depend on the decision variable at all. Verified on the repo's own
  `sample_parcels.csv`:

  ```
  vehicle         F0 (-util_w)   F1 (distance)   F2 (-compliance)  feasible
  BIKE               -0.508000        3.697415          -1.000000     False
  THREE_WHEEL        -0.084667        3.697415          -1.000000      True
  VAN                -0.012700        3.697415          -1.000000      True
  LORRY              -0.002540        3.697415          -1.000000      True
  ```

  Two of three objectives are constant across the entire search space. The problem
  collapses to "pick the smallest feasible box" over four discrete points, solvable
  exactly with one `min()` call. 80 individuals x 80 generations = 6,400 evaluations
  searching four points.

### 1.2 Stated handling constraints are not implemented

The research requires assignment to respect fragility, stackability, volume, width,
height and vehicle capacity. Actually enforced today: weight sum, and volume sum.
Volume-as-a-scalar-sum is the bin-packing fallacy — it says a 115 cm parcel fits in a
bike because the arithmetic works. Fragility appears only as a clustering feature,
never as a constraint. Stackability and the three dimension columns have no columns on
the `Parcel` model at all, so they cannot be enforced.

The upstream dataset carries all of it and the backend reads none of it: `length_cm`,
`width_cm`, `height_cm`, `stackable`, `max_stack_weight_kg`, `loading_orientation_fixed`,
`hazardous`, `requires_refrigeration`, `two_person_lift`, `do_not_tilt`, `priority_level`.

### 1.2b The vehicle catalog is hardcoded, and loading order is undefined

`optimization_service.VEHICLES` is a module-level Python dict. Capacities cannot be
changed without a deploy, cannot vary by depot, cannot be audited, and are not recorded
against the plans they produced — so results are not reproducible. The catalog belongs in
the database, queried at runtime.

Separately, nothing in the current code decides the **order parcels are loaded into the
vehicle**. `VirtualVehicle` records only aggregate used weight and volume. A load plan
that does not say what goes in first is not actionable by a loading crew: parcels for the
first stop end up buried behind parcels for the last. The plan must carry a delivery
sequence and a reverse (LIFO) load sequence with 3D positions.

### 1.3 Clustering feature scaling silences the non-spatial features

`clustering_service.feature_matrix` divides by fixed constants instead of standardising.
Measured contribution to squared Euclidean distance on real data:

```
lat 51.9%   lng 39.2%   weight 5.8%   volume 1.9%
fragile 0.75%   tw_start 0.25%   tw_end 0.23%
```

Time windows contribute under half a percent. The clusterer is using geography and
nothing else, which undercuts any claim that clustering respects delivery constraints.

### 1.4 Other defects

- HDBSCAN noise (`label == -1`) is stored as `cluster_id = -1` and then treated as a
  legitimate cluster by `cluster_summary` and by `POST /optimization/run`. Geographically
  scattered outliers get bundled onto one vehicle.
- Oversize clusters hard-fail: `optimize_load` raises `"No vehicle type is feasible"`
  and returns HTTP 400. No splitting, no fallback.
- No planning-instance concept. `train_hdbscan` runs `db.query(Parcel).all()` over the
  entire table with no depot or date filter — also a scalability failure.
- `seed=42` is hardcoded inside `minimize()`, making multi-seed statistical runs
  impossible without editing source.
- No K-Means baseline anywhere. No evaluation harness, no statistical test.
- `app/tests/test_health.py` is 14 lines checking two endpoints return 200. No
  feasibility-invariant tests exist.
- `import_csv` wraps every row in a bare `except Exception: skipped += 1`, hiding all
  data errors. No deduplication, no missing-value handling.
- `OptimizationResponse` omits `virtual_vehicle_id` although `optimize_load` returns it.
- `try_insert` validates only weight and volume, and calls deprecated `datetime.utcnow()`
  via `__import__` inside the function body.
- Every endpoint is unauthenticated; `jwt_secret_key` defaults to
  `"change-this-in-production"`.
- No CSV or JSON load-plan export, which is the product-facing deliverable to the
  downstream route-optimization module.

---

## 2. Execution rules

- **Work phase by phase, in order.** After each phase, run the test suite and report
  what passes. Do not begin the next phase until the current one is green.
- **Do not refactor beyond the phase you are in.** No opportunistic renames, no
  reformatting of untouched files.
- **Never reintroduce a weighted-sum scalarisation as the optimizer.** A scalar score
  may exist *only* as an optional post-hoc tie-breaker for picking one solution out of a
  genuine Pareto front, and it must be clearly named and documented as such.
- **Never discard the result of `minimize()`.** Assign it, use `res.F` and `res.X`.
- Every new module gets a docstring stating which proposal Specific Objective (SO1–SO6)
  or Functional Requirement (FR01–FR06) it satisfies.
- Preserve backwards compatibility of existing endpoint paths where practical; add new
  endpoints rather than repurposing old ones.
- Use type hints throughout. Target Python 3.13, SQLAlchemy 2.x style, Pydantic v2.

---

## Phase 0 — Baseline and safety net

1. Read the whole repo before changing anything. Produce a short written map: each
   module, its responsibility, and its callers.
2. Confirm the dependencies in `pyproject.toml`. Add if missing: `scikit-learn`,
   `scipy`, `pandas`, `pytest`. Confirm `hdbscan`, `pymoo`, `joblib`, `numpy` present.
3. Create `app/tests/conftest.py` with fixtures: an in-memory SQLite session, a
   deterministic synthetic parcel factory (seeded), and a `TestClient`.
4. Write `app/tests/test_baseline_smoke.py` that exercises the *current* pipeline
   end-to-end so you can detect regressions while refactoring. It is allowed to be
   deleted in Phase 3 once real tests replace it.

**Gate:** tests run and pass.

---

## Phase 1 — Data model: carry the constraints

**Goal:** the database must hold every attribute the optimizer needs to enforce.

### 1.1 Extend `app/models/parcel.py`

Add these columns to `Parcel` (all nullable with sensible defaults so existing rows
survive):

| Column | Type | Default | Purpose |
|---|---|---|---|
| `depot_id` | String(32), indexed | — | planning-instance key |
| `delivery_date` | Date, indexed | — | planning-instance key |
| `length_cm` | Float | — | dimensional fit |
| `width_cm` | Float | — | dimensional fit |
| `height_cm` | Float | — | dimensional fit |
| `stackable` | Boolean | True | stacking feasibility |
| `max_stack_weight_kg` | Float | 0.0 | load that may rest on top |
| `loading_orientation_fixed` | Boolean | False | cannot be rotated |
| `hazardous` | Boolean | False | requires certified vehicle |
| `hazmat_class` | String(16) | None | — |
| `requires_refrigeration` | Boolean | False | requires refrigerated vehicle |
| `temp_min_celsius` | Float | None | — |
| `temp_max_celsius` | Float | None | — |
| `two_person_lift` | Boolean | False | handling flag |
| `do_not_tilt` | Boolean | False | handling flag |
| `priority_level` | String(16) | 'standard' | urgency; one of standard/next_day/express/same_day |
| `service_type` | String(24) | 'door_to_door' | — |
| `special_handling` | Boolean, computed | False | derived: hazardous OR requires_refrigeration OR two_person_lift |

Add a `volume_m3` consistency check: if dimensions are present, assert
`abs(volume_m3 - l*w*h/1e6) < 1e-6` at import time and log a warning on mismatch
rather than silently accepting.

Add a composite index on `(depot_id, delivery_date)`.

### 1.2 Extend `app/models/virtual_vehicle.py`

Add: `depot_id`, `delivery_date`, `plan_id` (String, indexed — groups vehicles belonging
to one load plan), `parcel_count`, `max_parcels`, `estimated_distance_km`,
`time_window_compliance`, `fleet_cost`, `is_refrigerated`, `is_hazmat_certified`,
`cargo_length_cm`, `cargo_width_cm`, `cargo_height_cm`.

Add a new model `LoadPlan` with: `plan_id` (PK), `depot_id`, `delivery_date`,
`clustering_method` ('hdbscan' | 'kmeans'), `seed`, `n_parcels`, `n_vehicles`,
`mean_utilization`, `total_distance_km`, `mean_time_window_compliance`,
`total_fleet_cost`, `hypervolume`, `runtime_seconds`, `created_at`.

Add `app/models/parcel_assignment.py` — an association table linking `plan_id`,
`virtual_vehicle_id`, `parcel_id`, `delivery_sequence`, `load_sequence`, `stack_layer`,
`load_position_x`, `load_position_y`, `load_position_z`. This is what gets exported.

### 1.2b New model — the vehicle type catalog lives in the database

**The vehicle catalog must not be a hardcoded Python dict.** Today
`optimization_service.VEHICLES` is a module-level literal, which means capacities cannot
be changed without a code deploy, cannot differ per depot, and cannot be audited. Create
`app/models/vehicle_type.py`:

```python
class VehicleTypeCatalog(Base):
    __tablename__ = "vehicle_type_catalog"
    id, code (unique, e.g. "VAN"), display_name,
    capacity_kg, capacity_m3,
    cargo_length_cm, cargo_width_cm, cargo_height_cm,
    max_parcels, max_stack_layers,
    fixed_cost, cost_per_km, avg_speed_kmh,
    is_refrigerated, temp_min_celsius, temp_max_celsius,
    is_hazmat_certified, has_tail_lift,
    min_road_width_m,          # for narrow-lane eligibility later
    depot_id (nullable),        # null = available at every depot
    is_active (bool),
    created_at, updated_at
```

Add `app/services/vehicle_catalog_service.py` with:
- `list_available_types(db, depot_id, delivery_date) -> list[VehicleTypeCatalog]` —
  returns active types for that depot (including depot-agnostic rows). **This is the
  only way the optimizer may obtain vehicle data.** It must never import a literal dict.
- `get_type(db, code)`, `upsert_type(db, payload)`, `deactivate_type(db, code)`
- An in-request cache so a single pipeline run hits the table once, not per evaluation.

Add CRUD endpoints under `/api/v1/vehicle-types` (GET list, GET by code, POST, PATCH,
DELETE→deactivate) so capacities can be maintained without a deploy.

Add `app/db/seed_vehicle_types.py` seeding BIKE, THREE_WHEEL, VAN, LORRY with the
current placeholder figures, idempotently (upsert by `code`). Mark the seeded rows with
a `source` note of `"placeholder"` so it is obvious which rows still need real
Sri Lankan capacity and cost figures.

If `list_available_types` returns an empty set for an instance, the pipeline must raise a
clear, specific error — never fall back to a built-in default.

### 1.3 Alembic migration

Generate and commit a migration for all of the above. Do not rely on
`Base.metadata.create_all`.

### 1.4 Rewrite `app/services/data_service.py`

- Replace the bare `except Exception` with per-field validation that **collects** errors
  into a structured report: `{"inserted": n, "skipped": n, "errors": [{"row": i, "field": f, "reason": r}]}`.
- Add real preprocessing (this is SO1 and FR02, currently absent):
  - drop exact duplicate `parcel_id` rows, keeping the last, and count them
  - reject rows with missing `latitude`/`longitude`/`weight_kg`/`volume_m3`
  - impute missing dimensions from `volume_m3` assuming a cube, and flag the row
  - normalise time strings to `HH:MM`, reject and report anything else
  - validate lat/lng fall inside a configurable bounding box (default: Colombo region,
    lat 6.7–7.1, lng 79.7–80.1) and report out-of-region rows
  - coerce boolean-ish strings consistently in one helper
- Add a column-mapping layer so the rich 58-column upstream dataset can be imported
  directly. Accept both the current 8-column minimal format and the full format; map
  `dropoff_lat`→`latitude`, `dropoff_lng`→`longitude`, etc. Ignore any column that looks
  like optimizer output (`assigned_vehicle_id`, `assigned_route_id`, `stop_sequence`,
  `load_position_*`, `load_layer`, `actual_delivery_time`, `delivery_status`,
  `failure_reason`, `delivery_duration_minutes`) and **log an explicit warning naming
  them as target-leakage columns that were dropped.**

**Gate:** import the full upstream CSV successfully; error report is non-empty and
accurate on a deliberately corrupted fixture.

---

## Phase 2 — Clustering: fix scaling, handle noise, add the baseline

### 2.1 Rewrite `app/services/clustering_service.py`

**Feature construction.** Replace the fixed-constant division with an explicit,
documented two-block approach:

- Project lat/lng to local metric coordinates (equirectangular around the depot is
  adequate and cheap: `x = R*(lng-lng0)*cos(lat0)`, `y = R*(lat-lat0)`, in km). This
  removes the lat/lng scale asymmetry properly instead of papering over it.
- Standardise every feature with `sklearn.preprocessing.StandardScaler`, fitted per
  planning instance and persisted alongside the model.
- Apply explicit, config-driven weights *after* standardisation:
  `CLUSTER_FEATURE_WEIGHTS = {"spatial": 1.0, "time_window": 0.5, "urgency": 0.3}`.
  Document in the docstring that spatial dominance is now a deliberate, tunable choice
  rather than an accident of scaling.
- **Remove `fragile` from the feature vector.** Fragility is a handling constraint, not
  a spatial similarity signal; it belongs in the optimizer's constraint set, where
  Phase 3 puts it. Say so in the docstring.
- Time windows should enter as cyclical/interval features — use window midpoint and
  window width, both standardised, not raw start and end.

**Planning instances.** Every clustering call takes `(depot_id, delivery_date)` and
operates only on that subset. Add `get_planning_instance(db, depot_id, delivery_date)`.
Never call `db.query(Parcel).all()` again.

**Noise handling.** HDBSCAN's `-1` label must not become a pseudo-cluster. Implement
`handle_noise(parcels, labels, strategy)` with strategies:
- `"nearest_cluster"` (default) — assign each noise point to the nearest cluster centroid
  in metric space, but only if within `NOISE_MAX_ASSIGN_KM` (config, default 3.0 km)
- `"singleton"` — otherwise, each remaining noise point becomes its own cluster
Store the original label in a new `Parcel.is_noise` boolean so the dissertation can
report the noise rate honestly.

### 2.2 New file `app/services/baseline_clustering.py`

Implement the K-Means baseline (SO5 — currently entirely absent):

- Same feature pipeline, same planning-instance scoping, same interface signature as
  HDBSCAN so the evaluation harness can swap them.
- `k` selection must be principled and documented. Use
  `k = ceil(total_volume / mean_vehicle_capacity_m3)` as the capacity-derived estimate,
  then refine with silhouette score over `[k_est-2, k_est+2]`. Record the chosen `k`.
- Accept a `seed` parameter. Never hardcode it.

Both clusterers expose:
```python
def cluster(parcels: list[Parcel], seed: int, config: ClusteringConfig) -> ClusterResult
```
where `ClusterResult` carries `labels`, `n_clusters`, `noise_count`, `runtime_seconds`,
and method-specific metadata.

### 2.3 New file `app/services/capacity_aware_clustering.py`

This is the **research novelty** and it does not exist yet. It runs between clustering
and NSGA-II and must be independently switchable so its contribution can be ablated.

```python
def repair_clusters(clusters, vehicle_catalog, config) -> RepairedClusters
```

Three operations, applied in this order:

1. **Peel special-handling parcels.** Any parcel with `hazardous`,
   `requires_refrigeration`, or a `hazmat_class` is removed from its geometric cluster
   into a dedicated cluster keyed by its handling class. Rationale: these parcels
   constrain vehicle type absolutely, so leaving them in a general cluster forces the
   whole cluster onto an expensive certified vehicle.
2. **Split oversize clusters.** A cluster whose total weight or volume exceeds the
   largest catalog vehicle, or whose longest parcel dimension exceeds that vehicle's
   cargo bay, is recursively bisected. Use 2-means on the metric coordinates for the
   split so sub-clusters stay spatially coherent. Recurse until every sub-cluster fits
   at least one vehicle type. Cap recursion depth (config, default 6) and log if hit.
3. **Merge undersize clusters.** Two clusters are merge candidates if their combined
   load still fits one vehicle type AND their centroids are within
   `MERGE_MAX_CENTROID_KM` (config, default 2.0 km) AND their time windows overlap.
   Merge greedily, best pair first by a documented rule, until no candidate remains.

Return a full audit trail: how many clusters were split, merged, and peeled, and the
before/after cluster count. The dissertation needs these numbers.

**Gate:** unit tests prove that after `repair_clusters`, every cluster fits at least one
vehicle type, no parcel is lost, and no parcel is duplicated.

---

## Phase 3 — The NSGA-II rewrite (the core fix)

Rewrite `app/services/optimization_service.py` completely. This is the phase that
determines whether the dissertation stands up.

### 3.1 Vehicle catalog — sourced from the database

**Delete the module-level `VEHICLES` dict from `optimization_service.py` entirely.**
It must not be replaced by another literal elsewhere. The optimizer obtains vehicle data
by calling `vehicle_catalog_service.list_available_types(db, depot_id, delivery_date)`
(Phase 1.2b) once at the start of the run.

Load the returned ORM rows into an immutable in-memory snapshot for the duration of the
run, so the GA's inner loop does not touch the database:

```python
@dataclass(frozen=True)
class VehicleTypeSpec:
    code: str
    capacity_kg: float
    capacity_m3: float
    cargo_length_cm: float
    cargo_width_cm: float
    cargo_height_cm: float
    max_parcels: int
    max_stack_layers: int
    fixed_cost: float          # cost to deploy one, per day
    cost_per_km: float
    avg_speed_kmh: float
    is_refrigerated: bool
    temp_min_celsius: float | None
    temp_max_celsius: float | None
    is_hazmat_certified: bool
    has_tail_lift: bool

def load_catalog_snapshot(db, depot_id, delivery_date) -> tuple[VehicleTypeSpec, ...]
```

Record the exact snapshot (all fields, all types) in the `LoadPlan` row as a JSON column
`catalog_snapshot`. Results are not reproducible if someone edits a capacity between
runs and there is no record of what the optimizer actually saw. The evaluation harness
must fail loudly if two runs it is comparing used different snapshots.

`T` in the encoding (section 3.2) is `len(snapshot)`, derived at runtime — not a constant.
The system must work correctly if an administrator adds a fifth vehicle type through the
API without any code change. Add a test proving that.

The seeded rows carry placeholder capacity and cost figures. Add a note to the README
and a `source="placeholder"` marker on the rows: these must be replaced with real
Sri Lankan figures before final results are reported. Do not invent authoritative-looking
numbers.

### 3.2 Problem formulation

Create `app/optimization/assignment_problem.py`.

**Decision variables.** For a planning instance with `n` parcels and a vehicle-slot
budget `K`:

- Genes `0 .. n-1`: integer in `[0, K-1]` — which vehicle slot each parcel goes to.
- Genes `n .. n+K-1`: integer in `[0, T-1]` — the vehicle *type* of each slot,
  where `T = len(catalog)`.

Total `n_var = n + K`. Set `K = ceil(n / min_parcels_per_vehicle)` bounded by a config
`MAX_VEHICLE_SLOTS`; unused slots (no parcels assigned) contribute zero cost and are
dropped from the final plan. **This is the fix for the fatal defect: distance,
compliance and cost now genuinely vary with the decision variable.**

**Objectives — four, all minimised:**

| # | Objective | Formula |
|---|---|---|
| f1 | negative mean utilization | `-mean over used vehicles of max(weight_util, volume_util)` |
| f2 | total route distance | sum over used vehicles of nearest-neighbour tour from depot |
| f3 | negative time-window compliance | `-(compliant parcels / total parcels)` |
| f4 | total fleet cost | sum over used vehicles of `fixed_cost + cost_per_km * distance` |

Note f1 uses `max(weight, volume)` utilization, not weight alone — a van full of
pillows is fully utilized. Document this choice.

**Redefine time-window compliance.** The current pairwise-overlap metric measures
whether parcels *could* share a window; it does not measure whether deliveries *will*
be on time. Replace with a schedule-based metric: for each vehicle, walk its
nearest-neighbour tour, accumulate travel time from `avg_speed_kmh` plus a per-stop
service time (config, default 4 minutes, scaled by `two_person_lift`), and count a
parcel compliant if its arrival time falls inside `[time_window_start, time_window_end]`.
Keep the old pairwise function available under a clearly deprecated name for
comparison in the dissertation if useful.

**Constraints (`n_ieq_constr`), all expressed as `g(x) <= 0`:**

1. Weight overflow: `sum(weight) - capacity_kg` per vehicle, aggregated as sum of positives
2. Volume overflow: `sum(volume) - capacity_m3`, same aggregation
3. Parcel-count overflow: `count - max_parcels`
4. Dimensional fit: for each parcel, `longest_side - longest_cargo_dim` (respecting
   `loading_orientation_fixed` — if fixed, each of l/w/h must fit the corresponding
   cargo dimension without rotation)
5. Hazmat: any hazardous parcel on a non-certified vehicle
6. Refrigeration: any refrigerated parcel on a non-refrigerated vehicle, plus
   temperature-range compatibility
7. Stacking: total weight of non-fragile parcels assigned above a parcel must not exceed
   its `max_stack_weight_kg`; a `fragile` or non-`stackable` parcel must occupy a top
   layer. Model this with the shelf-stacking heuristic in 3.4 — you need a placement to
   evaluate it.
8. Empty-slot consistency: a slot with parcels must have a valid type (auto-satisfied
   by encoding, but assert it)

### 3.3 Algorithm configuration

```python
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.operators.sampling.rnd import IntegerRandomSampling
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM
from pymoo.operators.repair.rounding import RoundingRepair
```

- `sampling=IntegerRandomSampling()`
- `crossover=SBX(prob=0.9, eta=15, vtype=float, repair=RoundingRepair())`
- `mutation=PM(prob=1.0/n_var, eta=20, vtype=float, repair=RoundingRepair())`
- `eliminate_duplicates=True`
- **`seed` must be a function parameter threaded from the caller. Delete the hardcoded
  `seed=42`.**
- Population and generations from config, defaults 100 and 200 (raise from the current
  80/80 now that the search space is real).

**Add a warm-start seeding operator.** Inject into the initial population a small number
of individuals built from the capacity-aware repaired clusters — one cluster per vehicle
slot, with vehicle type chosen as the smallest feasible. This gives NSGA-II a feasible
starting region and is a defensible, documentable design choice.

**Add a custom repair operator** that fixes the most common infeasibility cheaply:
if a vehicle overflows, move its lightest parcels to the least-loaded compatible slot.
This is standard practice for constrained assignment GAs; document it.

### 3.4 Delivery sequence and loading order

Parcels must be loaded in an order that matches how they will be unloaded. Two distinct
orderings are involved and the code must keep them clearly separated:

**Delivery sequence** — the order stops are visited. The optimizer already computes a
nearest-neighbour tour per vehicle for objective f2; reuse that tour. Store it as
`ParcelAssignment.delivery_sequence` (1-based). Document explicitly, in the docstring
and in the export schema, that this is a **cost-estimation tour, not an optimized route**,
and that the downstream route-optimization module may reorder it. If it does, the loading
order must be recomputed from the new sequence — expose
`recompute_load_order(plan_id, new_sequence)` for that purpose. This keeps the scope
boundary intact: you are not doing route optimization, you are producing a load order
consistent with a stated delivery order.

**Load sequence** — the order parcels are physically placed into the vehicle, and it is
the **reverse** of the delivery sequence (last-in, first-out). The parcel delivered first
is loaded last and sits nearest the doors; the parcel delivered last is loaded first and
sits deepest in the bay. Store as `ParcelAssignment.load_sequence` (1-based, 1 = loaded
first = deepest).

Where LIFO conflicts with a physical constraint, physical constraints win, in this
priority order:

1. Stack-weight and fragility limits (a fragile parcel cannot be buried to satisfy LIFO)
2. Dimensional fit
3. Weight distribution — heavier parcels low, and roughly balanced front-to-back
4. LIFO accessibility

Record every LIFO violation the heuristic was forced to make in a
`load_order_exceptions` list on the plan, with the parcel id and the reason. Do not
silently ignore them; the count is a reportable quality metric.

### 3.5 Load placement heuristic

Create `app/optimization/placement.py`. A shelf-stacking heuristic that, given a parcel
set with an assigned delivery sequence and a vehicle's cargo dimensions, produces
`(x, y, z, layer, load_sequence)` for every parcel:

- Partition parcels into **delivery-stop bands**, processed in reverse delivery order
  (last stop first). Each band is placed deeper in the bay (larger `x`, measuring from
  the cargo doors inward) than the band after it. This is what makes the load LIFO.
- Within a band, sort heaviest-and-largest-footprint first
- Place along the cargo floor in rows, opening a new row when width is exhausted, and a
  new layer when the band's depth allocation is exhausted
- Never place any parcel on top of a parcel that is `fragile` or `not stackable`
- Never let the accumulated weight above a parcel exceed its `max_stack_weight_kg`
- Respect `loading_orientation_fixed` (no rotation) and `do_not_tilt`
- Prefer placing `two_person_lift` parcels on the floor layer near the doors, and note
  in the docstring that a vehicle with `has_tail_lift = False` should attract a penalty
  when carrying them
- Return `None` if no valid placement exists — this feeds constraint 7 in section 3.2

This is a feasibility and load-ordering heuristic, not a 3D bin-packing contribution.
Say so in the docstring so no examiner mistakes it for an unsubstantiated claim.

### 3.6 Solution selection from the front

Create `app/optimization/selection.py`.

- Return **the whole Pareto front** in the API response. This is non-negotiable —
  FR04 and SO4 require it.
- For the single plan that gets persisted, use **knee-point selection** by default:
  normalise all objectives to `[0,1]` using the front's ideal and nadir points, then
  pick the solution with minimum Euclidean distance to the ideal point. Document the
  formula.
- Support an optional caller-supplied preference weight vector for planner-driven
  selection (this is the decision-support story in the proposal). If supplied, it is
  applied **only** to choose among already-non-dominated solutions — never as the
  optimizer's objective.

### 3.7 Compute hypervolume

Use `pymoo.indicators.hv.HV` with a documented, fixed reference point derived from the
worst achievable value of each objective for the instance. Store on `LoadPlan`. You need
this for Phase 5.

**Gate:** on a fixture instance, `res.F` has more than one non-dominated row; objectives
f2, f3 and f4 take different values across the front (proving the fatal defect is fixed);
all constraints report satisfied for the selected solution.

---

## Phase 4 — Orchestration, persistence, export

### 4.1 New file `app/services/pipeline.py`

One function that runs the whole thing:

```python
def run_load_planning(
    db, depot_id, delivery_date, *,
    clustering_method: Literal["hdbscan","kmeans"] = "hdbscan",
    capacity_aware: bool = True,
    seed: int = 0,
    config: PipelineConfig,
) -> LoadPlanResult
```

Stages: load instance → preprocess → **load vehicle catalog snapshot from the database**
→ cluster → (optionally) capacity-aware repair → NSGA-II assignment → select solution →
derive delivery sequence per vehicle → compute LIFO load order and 3D placement →
persist `LoadPlan` (with `catalog_snapshot`), `VirtualVehicle` rows and
`ParcelAssignment` rows → return result with the full front.

Abort with a specific error if the catalog is empty, if any selected vehicle type is no
longer active, or if placement fails for the selected solution (in the last case, fall
back to the next-best solution on the front and record that this happened).

`capacity_aware=False` must produce a valid run — that is the ablation arm.

### 4.2 Export — the product deliverable

Create `app/services/export_service.py` producing the load plan in both formats the
downstream route-optimization module consumes.

**CSV** (`load_plan_{plan_id}.csv`), one row per parcel, sorted by
`virtual_vehicle_id` then `load_sequence` so the file reads in physical loading order:
```
plan_id, depot_id, delivery_date, virtual_vehicle_id, vehicle_type_code,
capacity_kg, capacity_m3, parcel_id, weight_kg, volume_m3,
length_cm, width_cm, height_cm, dropoff_lat, dropoff_lng,
time_window_start, time_window_end, priority_level,
fragile, stackable, hazardous, requires_refrigeration, two_person_lift,
delivery_sequence, load_sequence, stack_layer,
load_position_x, load_position_y, load_position_z
```

`delivery_sequence` is the estimated stop order the load was built against;
`load_sequence` is the physical loading order (reverse of delivery, LIFO). The downstream
route module owns `delivery_sequence` and may overwrite it — include a
`delivery_sequence_is_estimate` boolean column set to `true` to make that explicit.

**JSON** — nested: plan metadata → vehicles → parcels, with per-vehicle utilization,
estimated distance, compliance and cost. Include a `schema_version` field.

Endpoints:
- `POST /api/v1/optimization/plan` — run the pipeline, return the plan plus the front
- `GET  /api/v1/optimization/plan/{plan_id}` — retrieve
- `GET  /api/v1/optimization/plan/{plan_id}/export?format=csv|json` — download
- `GET  /api/v1/optimization/plan/{plan_id}/pareto` — the full front with objective values

### 4.3 Fix the existing endpoints

- Add `virtual_vehicle_id` to `OptimizationResponse` — currently returned by the service
  and dropped by the schema.
- Rename the `pareto_solutions` field's *contents* so it is a real front. If you keep the
  old `POST /optimization/run` endpoint, make it delegate to the new pipeline for a
  single cluster, and have it return a genuine front.
- Rewrite `try_insert` (dynamic parcel insertion) to check **all** constraints, not just
  weight and volume: dimensions, hazmat, refrigeration, stacking, parcel count. Replace
  `__import__("datetime").datetime.utcnow()` with a module-level
  `datetime.now(timezone.utc)`.
- Reject `cluster_id = -1` at the API boundary with a clear message, now that noise is
  handled upstream.

**Gate:** a full plan can be generated, persisted, retrieved and exported in both formats;
the exported CSV round-trips (re-importing it reproduces the same assignments).

---

## Phase 5 — Evaluation harness and statistical comparison

This is SO5, currently at zero. Build it as a standalone runnable module, not an endpoint.

Create `app/evaluation/` with:

### 5.1 `metrics.py`

Per-plan metrics: mean utilization (weight, volume, and max-of-both), total distance,
time-window compliance rate, total fleet cost, vehicle count, vehicles by type,
unassigned parcel count, constraint-violation count, hypervolume, runtime.

### 5.2 `experiment.py`

```python
def run_experiment(instances, methods, seeds, capacity_aware_variants, out_dir)
```

- `instances`: all `(depot_id, delivery_date)` pairs with at least `MIN_INSTANCE_PARCELS`
  parcels (config, default 100 — below this, capacity does not bind and the comparison
  is uninformative; document this filter and report how many instances it excluded)
- `methods`: `["hdbscan", "kmeans"]`
- `seeds`: `range(30)`
- Write one tidy row per `(instance, method, capacity_aware, seed)` to a CSV. Never
  aggregate before writing — keep raw runs so the analysis is auditable.
- Add a resume capability: skip runs whose row already exists. These experiments take
  hours.

### 5.3 `statistics.py`

- Aggregate to one value per `(instance, method)` by taking the **median across the 30
  seeds** — median, not mean, because GA outcomes are not normally distributed.
- Paired **Wilcoxon signed-rank test** (`scipy.stats.wilcoxon`) across instances, one
  test per metric, HDBSCAN vs K-Means.
- Report effect size (matched-pairs rank-biserial correlation) alongside every p-value.
  A p-value alone is not a result.
- Apply Holm–Bonferroni correction across the metric family and report both raw and
  adjusted p-values.
- Run the same test for the capacity-aware ablation (capacity_aware True vs False,
  HDBSCAN only).
- Emit a markdown results table ready to paste into the dissertation, with n, medians,
  IQRs, W statistic, p, adjusted p, and effect size.

### 5.4 `cli.py`

`python -m app.evaluation.cli run --seeds 30 --out results/`
`python -m app.evaluation.cli analyse --in results/runs.csv`

**Gate:** a reduced run (3 instances x 3 seeds) completes and produces a valid results
table. Do not fabricate or hand-edit any numbers at any point.

---

## Phase 6 — Tests: feasibility invariants

Replace the 14-line health test with a real suite in `app/tests/`.

### `test_feasibility_invariants.py` — the important one

For every generated plan, assert:
1. **Conservation** — every input parcel appears in exactly one vehicle. No losses, no
   duplicates. Compare sets, not counts.
2. **Weight** — per vehicle, `sum(weight) <= capacity_kg`.
3. **Volume** — per vehicle, `sum(volume) <= capacity_m3`.
4. **Count** — per vehicle, `n_parcels <= max_parcels`.
5. **Dimensions** — every parcel physically fits its vehicle's cargo bay, honouring
   `loading_orientation_fixed`.
6. **Fragility** — no parcel rests on a `fragile` or non-`stackable` parcel.
7. **Stack weight** — accumulated weight above any parcel `<= max_stack_weight_kg`.
8. **Hazmat** — hazardous parcels only on certified vehicles.
9. **Refrigeration** — refrigerated parcels only on refrigerated vehicles, with
   compatible temperature ranges.
10. **Placement validity** — no two parcels overlap in the placement coordinates; nothing
    exceeds the cargo bay bounds.
11. **Load order completeness** — every parcel has a `delivery_sequence` and a
    `load_sequence`; both are contiguous 1..n within each vehicle with no gaps or
    duplicates.
12. **LIFO consistency** — for every pair of parcels on the same vehicle, if A is
    delivered before B then A's placement depth is no greater than B's, *unless* the pair
    appears in `load_order_exceptions` with a recorded physical reason.
13. **Catalog fidelity** — every vehicle in the plan references a `vehicle_type_code`
    present in the plan's `catalog_snapshot`, and its capacities match the snapshot
    exactly. No plan may reference a type that is not in the database.

Run these as property-based tests over randomly generated instances (seeded, so failures
reproduce). If `hypothesis` is acceptable, use it; otherwise a seeded loop of 50
instances is adequate.

### Other test files

- `test_clustering.py` — noise handling, planning-instance scoping, scaler determinism
  under a fixed seed, K-Means/HDBSCAN interface parity
- `test_capacity_aware.py` — post-repair every cluster fits some vehicle; split/merge/peel
  counts are correct; parcel conservation holds
- `test_nsga2.py` — **explicitly assert that the Pareto front contains more than one
  solution and that f2, f3, f4 vary across it.** This is the regression test for the
  fatal defect. Also assert `minimize()`'s result is actually used.
- `test_vehicle_catalog.py` — types are read from the database and nowhere else; adding a
  fifth type through the API changes the optimizer's search space with no code change;
  deactivating a type removes it from subsequent plans; an empty catalog raises rather
  than falling back to a default. Add a grep-style assertion that no vehicle capacity
  literal remains in `app/services/` or `app/optimization/`.
- `test_placement.py` — LIFO ordering holds against a known delivery sequence; forced
  exceptions are recorded rather than silent; `recompute_load_order` produces a valid
  load order when the downstream module supplies a different delivery sequence
- `test_export.py` — CSV/JSON round-trip; rows emerge in loading order
- `test_data_service.py` — error reporting, duplicate handling, leakage-column rejection
- `test_api.py` — endpoint contracts

**Gate:** `pytest` green, and coverage reported for `app/services` and `app/optimization`.

---

## Phase 7 — Configuration and reproducibility

Rewrite `app/core/config.py`:

- Group settings into nested models: `ClusteringConfig`, `CapacityAwareConfig`,
  `NSGAConfig`, `EvaluationConfig`, `SecurityConfig`.
- Every magic number found in the codebase moves here with a comment explaining it.
- Add `random_seed` as a top-level setting and thread it everywhere. **No `seed=42`
  literal may remain anywhere outside tests.**
- Add a `reproducibility.py` helper that sets and records numpy/python seeds and dumps a
  run manifest (config snapshot, git commit, library versions) into every results directory.

Update `.env.example` with every new variable.

---

## Phase 8 — Security, docs, cleanup

- Implement real JWT auth in `app/core/security.py` and `app/api/deps.py`
  (`get_current_user`). Apply the dependency to every parcel, optimization and
  virtual-vehicle endpoint. Leave the teammate's placeholder routers alone.
- Make `jwt_secret_key` mandatory with no default — fail loudly at startup if unset.
- Add rate limiting on the expensive `POST /optimization/plan` endpoint.
- Delete all committed `__pycache__` directories and add a `.gitignore`.
- Rewrite `README.md` to describe the real pipeline: instance loading → preprocessing →
  clustering (HDBSCAN or K-Means) → capacity-aware repair → NSGA-II assignment →
  knee-point selection → placement → export. Include a mapping table from each module to
  the proposal's SO1–SO6 and FR01–FR06.
- Add `docs/DESIGN_DECISIONS.md` recording, with justification: the four objectives and
  why fleet cost was added beyond the proposal's three; the virtual-vehicle catalog
  approach versus the proposal's fixed depot fleet; HDBSCAN replacing the proposal's
  DBSCAN; the utilization definition; the knee-point rule; the repair operator; the
  instance-size filter. **Your supervisor will want these divergences written up as
  deliberate design refinement following pilot experiments, not discovered as
  discrepancies during the viva.**

---

## Definition of done

- [ ] `minimize()`'s return value is used; no weighted-sum scalarisation acts as the optimizer
- [ ] Decision variable is a parcel→vehicle assignment; f2, f3, f4 provably vary across the front
- [ ] Four objectives, and constraints covering weight, volume, count, dimensions, hazmat,
      refrigeration, fragility and stack weight
- [ ] Vehicle types are read from the `vehicle_type_catalog` table at runtime; no capacity
      or cost literal remains anywhere in the services or optimization packages
- [ ] Each plan stores the `catalog_snapshot` it was optimized against
- [ ] Adding a vehicle type through the API changes the optimizer's search space with no
      code change, proven by a test
- [ ] Every parcel has a delivery sequence and a LIFO load sequence with 3D coordinates;
      forced LIFO exceptions are recorded, not hidden
- [ ] `recompute_load_order` lets the downstream route module reorder stops without
      invalidating the load plan
- [ ] `/optimization/plan/{id}/pareto` returns a genuine multi-solution front
- [ ] Clustering features standardised; `fragile` removed from the feature vector;
      noise handled explicitly
- [ ] `capacity_aware_clustering.py` exists, is switchable, and is covered by tests
- [ ] K-Means baseline implemented with the same interface
- [ ] Evaluation harness runs 30 seeds across instances and emits a Wilcoxon table with
      effect sizes and Holm correction
- [ ] All ten feasibility invariants tested and passing
- [ ] Load plan exports as CSV and JSON and round-trips
- [ ] No hardcoded seed outside tests; run manifests written
- [ ] Every endpoint authenticated; no default secret
- [ ] `docs/DESIGN_DECISIONS.md` records every divergence from the proposal

---

## Final instruction

Work through the phases in order. After each phase, report: files changed, tests added,
tests passing, and anything in this specification you could not implement as written
along with why. If a requirement here is wrong or infeasible given the codebase, say so
rather than silently substituting something else — a wrong specification faithfully
reported is fixable; a silent substitution discovered at the viva is not.
