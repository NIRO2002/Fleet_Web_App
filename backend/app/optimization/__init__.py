"""NSGA-II assignment problem, load placement and solution selection (Phase 3).

Satisfies SO3/SO4/FR04: replaces the pre-remediation `n_var=1`
"pick-one-vehicle-type-for-a-fixed-parcel-list" formulation with a genuine
parcel-to-vehicle-slot assignment problem, a physical loading-order
heuristic, and multi-objective solution selection. Nothing in this package
may contain a vehicle capacity literal — vehicle data always comes from
`app.services.vehicle_catalog_service`.
"""
