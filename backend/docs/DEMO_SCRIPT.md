# Supervisor Demo Script — Loaded Vehicles / READY handoff

Five-minute walkthrough of the business flow: parcels in, vehicles selected and loaded,
a loaded vehicle marked READY for the fleet optimizer to collect.

**Before the meeting**: pre-generate a load plan so a slow optimization run can't derail
the demo. `D-CMB-001 / 2026-01-05` already has one (`PLAN-3AFA453138`, verified against the
real dataset — 3 vehicles, 40 parcels, one already marked READY). Keep the live
`Generate Load Plan` button available only as a bonus if time allows.

## 1. Show the parcel dataset

Open **Parcel Consolidation**. Point out the parcel count and the depot/delivery-date
scoping — this is the real 36,000-row dataset (90 real instances, 3 depots x 30 dates), not
synthetic data.

## 2. Generate a load plan

Open **Loaded Vehicles**, pick a depot and delivery date. If no plan exists yet, press
**Generate Load Plan** and narrate while it runs: parcels are clustered (HDBSCAN), then
NSGA-II searches vehicle-type/load assignments across four objectives (utilization,
distance, time-window compliance, fleet cost) for a couple hundred generations — this is
why it takes minutes, not seconds. If a plan already exists for that depot/date, it loads
immediately instead of re-running.

## 3. Show the Loaded Vehicles page

Point out the vehicle cards: different vehicle types, parcel counts, utilization, weight
and volume figures, and the summary bar (vehicles, how many READY, aggregate utilization).
Status badges are amber (LOADING) or green (READY).

## 4. Open the 3D view

Press **View 3D Load** on a vehicle. Drag to orbit, scroll to zoom. Switch the colour mode
to stack layer to show the load isn't flat — parcels genuinely occupy multiple layers.
Drag the load-sequence slider from the Load Plan page's own 3D tab (or narrate it here) and
explain LIFO: the first parcel delivered is loaded *last*, closest to the doors, so the
driver never has to dig through the load to reach it.

## 5. Press READY

From either the card or the 3D modal, press **Ready**. The badge flips immediately
(optimistic update), then confirms against the backend. Refresh the page to show it
persisted — this isn't just client state.

## 6. Call the fleet-optimizer handoff

Open a new tab (or curl) to:

```
GET /api/v1/vehicles/ready?depot_id=D-CMB-001&delivery_date=2026-01-05
```

Show the vehicle appearing with its full stop list (parcel id, lat/lng, delivery sequence,
time window) — this is the exact payload the teammate's route optimizer consumes. Note
that `deliverySequence` is explicitly a nearest-neighbour estimate here, not an optimized
route; reordering stops is the downstream module's job.

## Fallback

If WebGL fails on the demo machine, the Load Plan page's table tab shows the same data
sorted by load sequence — same manifest, no 3D required.
