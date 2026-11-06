from __future__ import annotations

import pandas as pd

from eaidrs.core.config import DatasetConfig
from eaidrs.data import audit, schema
from eaidrs.data.loading import load_clean_dataset
from tests.conftest import FixtureDataset


def test_class_by_day_counts_match_fixture(
    fixture_dataset: FixtureDataset, base_config: DatasetConfig
) -> None:
    dataset = load_clean_dataset(fixture_dataset.config, fixture_dataset.raw_dir)
    # Full Mon-Fri order: days without a fixture file must appear as zero columns.
    table = audit.class_by_day(dataset.frame, base_config.day_order)
    for (day, label), count in fixture_dataset.expected_counts.items():
        assert table.loc[label, day] == count
    assert table.loc["TOTAL", "total"] == sum(fixture_dataset.expected_counts.values())
    assert table.loc["BENIGN", "wednesday"] == 0  # no Wednesday file in the fixture


def test_quality_table_and_inventory(fixture_dataset: FixtureDataset) -> None:
    dataset = load_clean_dataset(fixture_dataset.config, fixture_dataset.raw_dir)
    quality = audit.quality_table(dataset.reports, dataset.feature_columns)
    assert quality.loc["Flow Bytes/s", "infinite"] == 1
    assert quality.loc["Flow Bytes/s", "missing_after_cleaning"] == 2
    inventory = audit.file_inventory(dataset, file_sizes={})
    assert inventory["rows_kept"].sum() == len(dataset.frame)
    assert inventory.loc[inventory["day"] == "thursday", "blank_rows_dropped"].item() == 3


def test_class_time_ranges_show_attack_episodes(fixture_dataset: FixtureDataset) -> None:
    dataset = load_clean_dataset(fixture_dataset.config, fixture_dataset.raw_dir)
    episodes = audit.class_time_ranges(dataset.frame).set_index(schema.LABEL)
    ssh = episodes.loc["SSH-Patator"]
    assert ssh["flows"] == 20
    assert ssh["first_timestamp"] == pd.Timestamp("2017-07-04 14:00")


def test_duplicates_and_cross_split_duplicates() -> None:
    frame = pd.DataFrame({"f": [1.0, 1.0, 2.0, 1.0], schema.LABEL: ["A", "A", "B", "A"]})
    split = pd.Series(["train", "train", "val", "test"])
    assert audit.duplicate_row_count(frame, ["f", schema.LABEL]) == 2
    assert audit.cross_split_duplicates(frame, split, ["f", schema.LABEL]) == {"val": 0, "test": 1}


def test_constant_columns() -> None:
    frame = pd.DataFrame({"a": [0.0, 0.0, None], "b": [1.0, 2.0, 3.0]})
    assert audit.constant_columns(frame, ["a", "b"]) == ["a"]


def test_markdown_table_renders() -> None:
    table = pd.DataFrame({"n": [1, 2]}, index=pd.Index(["x", "y"], name="label"))
    assert audit.markdown_table(table).splitlines() == [
        "| label | n |",
        "|---|---|",
        "| x | 1 |",
        "| y | 2 |",
    ]
