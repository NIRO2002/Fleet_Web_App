import asyncio
from datetime import date
from types import SimpleNamespace

import numpy as np
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from app.api.v1 import optimization as optimization_api
from app.models.parcel import Parcel
from app.schemas.optimization import OptimizationRequest
from app.services import clustering_service
from app.services.capacity_aware_clustering import RepairedClusters
from app.services.clustering_common import get_planning_instance


def _parcel(parcel_id, delivery_date, status="PENDING"):
    return Parcel(
        parcel_id=parcel_id, depot_id="D-CMB-001", delivery_date=delivery_date,
        status=status, latitude=6.9271, longitude=79.8612, weight_kg=2,
        volume_m3=0.01, time_window_start="08:00", time_window_end="12:00",
    )


def test_cluster_repair_and_optimization_resolve_the_same_carryover_set(monkeypatch):
    async def scenario():
        target = date(2026, 1, 5)
        client = AsyncMongoMockClient()
        await init_beanie(database=client.carryover_invariant, document_models=[Parcel])
        await Parcel.insert_many([
            _parcel("TODAY", target),
            _parcel("CARRY-PENDING", date(2026, 1, 4)),
            _parcel("CARRY-FAILED", date(2026, 1, 3), "FAILED"),
            _parcel("UNASSIGNED", date(2026, 1, 2)),
        ])

        collection = Parcel.get_motor_collection()
        async def compatible_bulk_write(operations):
            for operation in operations:
                await collection.update_one(operation._filter, operation._doc)
        monkeypatch.setattr(collection, "bulk_write", compatible_bulk_write)

        loaded = await get_planning_instance("D-CMB-001", target)
        loaded_count = len(loaded)
        assert loaded_count == 4

        def fake_cluster(parcels, seed, config):
            labels = []
            for parcel in parcels:
                parcel.cluster_id = 0 if parcel.parcel_id in {"TODAY", "CARRY-PENDING"} else 1
                parcel.cluster_probability = 1.0
                parcel.is_noise = False
                labels.append(parcel.cluster_id)
            return SimpleNamespace(
                labels=np.array(labels), n_clusters=2, noise_count=0,
                runtime_seconds=0.0, metadata={"model": object(), "scaler": object()},
            )
        monkeypatch.setattr(clustering_service, "cluster", fake_cluster)
        monkeypatch.setattr(clustering_service.joblib, "dump", lambda *_args, **_kwargs: None)

        _result, clustered = await clustering_service.train_hdbscan("D-CMB-001", target)

        async def fake_catalog(_depot_id): return [object()]
        monkeypatch.setattr(clustering_service, "list_available_types", fake_catalog)

        def fake_repair(_groups, _catalog, _config, _lat, _lon, seed=0):
            by_id = {p.parcel_id: p for p in clustered}
            return RepairedClusters(
                clusters={
                    0: [by_id["TODAY"], by_id["CARRY-PENDING"]],
                    1: [by_id["CARRY-FAILED"]],
                    2: [by_id["UNASSIGNED"]],
                },
                clusters_before=2, clusters_after=3,
                cluster_status={
                    0: {"feasible": True, "reason": None},
                    1: {"feasible": True, "reason": None},
                    2: {"feasible": False, "reason": "no_fitting_vehicle"},
                },
                excluded_infeasible_count=1,
            )
        monkeypatch.setattr(clustering_service, "repair_clusters", fake_repair)
        repaired = await clustering_service.repair_planning_instance(
            "D-CMB-001", clustered, depot_lat=6.9271, depot_lon=79.8612,
        )
        repaired_unassigned = next(p for p in clustered if p.parcel_id == "UNASSIGNED")
        assert repaired_unassigned.is_noise is False
        assert repaired_unassigned.cluster_id == -1
        assert repaired_unassigned.unassigned_reason == "NO_FITTING_VEHICLE"

        async def fake_get_depot(_depot_id):
            return SimpleNamespace(lat=6.9271, lng=79.8612, operating_hours_end="20:00", vehicle_capacity=20)
        async def fake_optimize(parcels, **_kwargs):
            return {"n_parcels": len(parcels), "parcel_ids": [p.parcel_id for p in parcels]}, None
        monkeypatch.setattr(optimization_api, "get_depot_or_fail", fake_get_depot)
        monkeypatch.setattr(optimization_api, "optimize_load", fake_optimize)

        planned_count = 0
        for cluster_id in (0, 1):
            expected = len(repaired.clusters[cluster_id])
            result = await optimization_api.run(OptimizationRequest(
                cluster_id=cluster_id, depot_id="D-CMB-001", delivery_date=target,
            ))
            assert result["n_parcels"] == expected
            planned_count += result["n_parcels"]

        unassigned = await Parcel.find({
            "depot_id": "D-CMB-001", "delivery_date": target, "cluster_id": -1,
        }).count()
        assert planned_count + unassigned == loaded_count

    asyncio.run(scenario())
