"""Fix Pass 4 item S5: structural guarantees about `data/parcels_sample_36000.csv`
that the rest of the test suite and the evaluation harness rely on. Codifies
the manual verification done before this pass started, so a future dataset
swap can't silently break an assumption other tests depend on."""
import pandas as pd

from app.evaluation.real_data import DATASET_PATH, list_instances, real_instance_payloads


def test_dataset_has_90_instances_of_exactly_400_parcels():
    instances = list_instances()
    assert len(instances) == 90
    for depot_id, delivery_date in instances:
        payloads = real_instance_payloads(depot_id, delivery_date)
        assert len(payloads) == 400, f"{depot_id}/{delivery_date} has {len(payloads)} parcels, expected 400"


def test_dataset_spans_three_depots_and_thirty_dates():
    instances = list_instances()
    depots = {depot_id for depot_id, _ in instances}
    dates = {delivery_date for _, delivery_date in instances}
    assert len(depots) == 3
    assert len(dates) == 30


def test_hazmat_class_is_null_exactly_where_hazardous_is_false():
    """The `'none'`-string sentinel Fix Pass 3 flagged as a risk (from an
    older 5,000-row sample) does not exist in this dataset -- guard against
    a future dataset swap reintroducing it."""
    df = pd.read_csv(DATASET_PATH)
    assert (df["hazmat_class"].astype(str).str.lower() == "none").sum() == 0

    hazardous_rows = df[df["hazardous"] == True]  # noqa: E712
    non_hazardous_rows = df[df["hazardous"] == False]  # noqa: E712
    assert hazardous_rows["hazmat_class"].notna().all()
    assert non_hazardous_rows["hazmat_class"].isna().all()


def test_no_duplicate_parcel_ids_and_no_missing_core_fields():
    df = pd.read_csv(DATASET_PATH)
    assert df["parcel_id"].duplicated().sum() == 0
    assert df[["weight_kg", "length_cm", "width_cm", "height_cm", "volume_m3"]].isna().sum().sum() == 0


def test_zero_stack_headroom_is_only_the_non_stackable_sentinel():
    df = pd.read_csv(DATASET_PATH)
    zero_headroom = df["max_stack_weight_kg"].eq(0)
    non_stackable = ~df["stackable"].astype(bool)

    assert zero_headroom.sum() == 15_000
    assert zero_headroom.equals(non_stackable)
    assert not (df["fragile"].astype(bool) & ~non_stackable).any()
