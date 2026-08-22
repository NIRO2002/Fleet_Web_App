import numpy as np

from app.db.seed_vehicle_types import FIELD_DATA_VEHICLE_TYPES
from app.evaluation.clustering_feature_experiment import load_instances
from app.optimization.assignment_problem import AssignmentConfig, VehicleTypeSpec, decode, run_nsga2
from app.optimization.selection import select_solution
from app.services.capacity_aware_clustering import group_by_cluster, repair_clusters
from app.services.clustering_common import ClusteringConfig
from app.services.clustering_service import cluster


def _catalog():
    return tuple(VehicleTypeSpec(
        code=v.code, capacity_kg=v.capacity_kg, capacity_m3=v.capacity_m3,
        cargo_length_cm=v.cargo_length_cm, cargo_width_cm=v.cargo_width_cm,
        cargo_height_cm=v.cargo_height_cm, max_parcels=v.max_parcels,
        max_stack_layers=v.max_stack_layers, fixed_cost=v.fixed_cost,
        cost_per_km=v.cost_per_km, avg_speed_kmh=v.avg_speed_kmh,
        has_tail_lift=v.has_tail_lift,
        vehicle_max_stack_weight_kg=v.vehicle_max_stack_weight_kg,
        available_from=v.available_from, available_until=v.available_until,
    ) for v in FIELD_DATA_VEHICLE_TYPES)


def _run():
    source = next(iter(load_instances().values()))[:12]
    parcels = [p.model_copy(deep=True) for p in source]
    cluster(parcels, 17, ClusteringConfig(min_cluster_size=5, min_samples=3))
    repaired = repair_clusters(group_by_cluster(parcels), FIELD_DATA_VEHICLE_TYPES, seed=17)
    config = AssignmentConfig()
    problem, result = run_nsga2(
        parcels, _catalog(), config, seed=17,
        warm_start_clusters=repaired.clusters,
    )
    chosen, objectives, decisions, constraints = select_solution(result)
    slots, types = decode(decisions[chosen], problem.n, problem.K)
    assignment = sorted(
        (parcels[index].parcel_id, slot, _catalog()[int(types[slot])].code)
        for slot, indexes in slots.items() for index in indexes
    )
    return assignment, objectives, constraints


def test_full_pipeline_is_semantically_reproducible():
    assignment_a, objectives_a, constraints_a = _run()
    assignment_b, objectives_b, constraints_b = _run()
    assert assignment_a == assignment_b
    assert np.array_equal(objectives_a, objectives_b)
    assert np.array_equal(constraints_a, constraints_b)
