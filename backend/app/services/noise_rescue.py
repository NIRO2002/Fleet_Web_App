"""Deterministic, catalog-feasible rescue of original HDBSCAN noise."""
from dataclasses import dataclass, field
import numpy as np

from app.services.cluster_feasibility import fits_some_vehicle_details
from app.services.clustering_common import project_to_metric


@dataclass
class NoiseRescueResult:
    joined_existing_count: int = 0
    rescue_group_count: int = 0
    rescue_group_parcel_count: int = 0
    singleton_count: int = 0
    unresolved_count: int = 0
    audit: list[dict] = field(default_factory=list)

    def summary(self):
        return {k: getattr(self, k) for k in (
            "joined_existing_count", "rescue_group_count", "rescue_group_parcel_count",
            "singleton_count", "unresolved_count",
        )}


def rescue_noise(parcels, vehicle_catalog, config, repair_config=None):
    result = NoiseRescueResult()
    real = {}
    noise = []
    for parcel in parcels:
        if parcel.cluster_id == -1:
            parcel.is_noise = True
            noise.append(parcel)
        else:
            real.setdefault(parcel.cluster_id, []).append(parcel)
            parcel.cluster_assignment_status = "NORMAL_CLUSTER"
            parcel.noise_resolution = None
            parcel.unassigned_reason = None
    noise.sort(key=lambda p: p.parcel_id)
    coords = {p.parcel_id: project_to_metric([p], config.depot_lat, config.depot_lon)[0] for p in parcels}

    remaining = []
    for parcel in noise:
        candidates = []
        for cid, members in real.items():
            centroid = np.mean([coords[p.parcel_id] for p in members], axis=0)
            distance = float(np.linalg.norm(coords[parcel.parcel_id] - centroid))
            if distance <= config.noise_max_assign_km:
                candidates.append((distance, cid))
        assigned = False
        for distance, cid in sorted(candidates):
            check = fits_some_vehicle_details(real[cid] + [parcel], vehicle_catalog, repair_config,
                                              config.depot_lat, config.depot_lon)
            if check.feasible:
                real[cid].append(parcel); parcel.cluster_id = cid
                parcel.cluster_assignment_status = "NOISE_RESCUED"
                parcel.noise_resolution = "NEAREST_FEASIBLE_CLUSTER"; parcel.unassigned_reason = None
                result.joined_existing_count += 1; assigned = True
                result.audit.append({"parcel_id": parcel.parcel_id, "original_cluster_id": -1,
                                     "resolution": parcel.noise_resolution, "target_cluster_id": cid,
                                     "distance_km": distance, "feasible": True})
                break
        if not assigned: remaining.append(parcel)

    next_id = max(real, default=-1) + 1
    pending = list(remaining); remaining = []
    while pending:
        seed = pending.pop(0); group = [seed]
        nearby = sorted((float(np.linalg.norm(coords[seed.parcel_id] - coords[p.parcel_id])), p.parcel_id, p) for p in pending)
        for distance, _pid, candidate in nearby:
            if distance > config.noise_group_max_km: continue
            if fits_some_vehicle_details(group + [candidate], vehicle_catalog, repair_config,
                                         config.depot_lat, config.depot_lon).feasible:
                group.append(candidate)
        if len(group) >= 2:
            for parcel in group:
                if parcel is not seed: pending.remove(parcel)
                parcel.cluster_id = next_id; parcel.cluster_assignment_status = "NOISE_RESCUED"
                parcel.noise_resolution = "RESCUE_GROUP"; parcel.unassigned_reason = None
                result.audit.append({"parcel_id": parcel.parcel_id, "original_cluster_id": -1,
                                     "resolution": "RESCUE_GROUP", "target_cluster_id": next_id, "feasible": True})
            real[next_id] = group; next_id += 1
            result.rescue_group_count += 1; result.rescue_group_parcel_count += len(group)
        else: remaining.append(seed)

    for parcel in remaining:
        check = fits_some_vehicle_details([parcel], vehicle_catalog, repair_config,
                                          config.depot_lat, config.depot_lon)
        if check.feasible:
            parcel.cluster_id = next_id; next_id += 1
            parcel.cluster_assignment_status = "NOISE_RESCUED"; parcel.noise_resolution = "SINGLETON"
            parcel.unassigned_reason = None; result.singleton_count += 1
            result.audit.append({"parcel_id": parcel.parcel_id, "original_cluster_id": -1,
                                 "resolution": "SINGLETON", "target_cluster_id": parcel.cluster_id,
                                 "feasible": True})
        else:
            parcel.cluster_id = -1; parcel.cluster_assignment_status = "UNASSIGNED"
            parcel.noise_resolution = "UNRESOLVED"; parcel.unassigned_reason = check.reason or "UNKNOWN"
            result.unresolved_count += 1
            result.audit.append({"parcel_id": parcel.parcel_id, "original_cluster_id": -1,
                                 "resolution": "UNRESOLVED", "target_cluster_id": -1,
                                 "feasible": False, "reason": parcel.unassigned_reason})
    return result


def assert_complete_cluster_assignment(parcels):
    ids = [p.parcel_id for p in parcels]
    if len(ids) != len(set(ids)): raise AssertionError("duplicate parcel ids after clustering")
    invalid = [p.parcel_id for p in parcels if p.cluster_id is None or (p.cluster_id == -1 and not p.unassigned_reason)]
    if invalid: raise AssertionError(f"incomplete cluster assignment: {invalid}")
