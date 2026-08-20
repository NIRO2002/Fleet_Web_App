import json

from app.core.reproducibility import write_manifest
from app.evaluation.harness import evaluation_catalog_snapshot


def test_evaluation_manifest_records_commit_dataset_catalog_and_config(tmp_path):
    dataset = tmp_path / "parcels.csv"
    dataset.write_text("parcel_id\nP-1\n")
    destination = tmp_path / "manifest.json"

    write_manifest(
        destination,
        catalog=evaluation_catalog_snapshot(),
        dataset_path=dataset,
        experiment_config={"population": 100, "generations": 200},
        extra={"seeds": [0, 1, 2], "enforce_weight_order": False},
    )
    manifest = json.loads(destination.read_text())

    assert manifest["git_commit_sha"]
    assert len(manifest["git_commit_sha"]) == 40
    assert manifest["dataset"]["filename"] == "parcels.csv"
    assert len(manifest["dataset"]["sha256"]) == 64
    assert manifest["catalog_snapshot_digest"]
    assert manifest["config_snapshot"]["experiment"]["generations"] == 200
    assert manifest["package_versions"].keys() >= {
        "pymoo", "hdbscan", "scikit-learn", "numpy", "scipy", "pandas",
    }
    assert manifest["enforce_weight_order"] is False
