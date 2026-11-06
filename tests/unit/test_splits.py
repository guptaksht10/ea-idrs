"""Chronological split tests: no overlap, correct ordering, determinism, no random splitting."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from eaidrs.core.config import SplitConfig, SplitFractions
from eaidrs.data import schema
from eaidrs.data.loading import load_clean_dataset
from eaidrs.data.splits import (
    assign_splits,
    check_split_invariants,
    class_split_counts,
    split_summary,
)
from tests.conftest import FixtureDataset

GLOBAL = SplitConfig(
    name="global",
    strategy="global_time",
    val_start=dt.datetime(2017, 7, 4),
    test_start=dt.datetime(2017, 7, 6),
    min_class_support=5,
)
GROUPED = SplitConfig(
    name="grouped",
    strategy="grouped_time",
    group_by=["day", "label"],
    fractions=SplitFractions(train=0.6, val=0.2, test=0.2),
    min_class_support=5,
)


def _frame(timestamps: list[str], labels: list[str] | None = None) -> pd.DataFrame:
    n = len(timestamps)
    return pd.DataFrame(
        {
            schema.TIMESTAMP: pd.to_datetime(timestamps),
            schema.DAY: ["monday"] * n,
            schema.LABEL: labels or ["BENIGN"] * n,
        }
    )


@pytest.fixture(scope="module")
def clean_frame(fixture_dataset: FixtureDataset) -> pd.DataFrame:
    return load_clean_dataset(fixture_dataset.config, fixture_dataset.raw_dir).frame


@pytest.mark.parametrize("config", [GLOBAL, GROUPED], ids=["global_time", "grouped_time"])
def test_every_row_assigned_once_with_no_temporal_overlap(
    clean_frame: pd.DataFrame, config: SplitConfig
) -> None:
    split = assign_splits(clean_frame, config)
    assert split.notna().all()
    assert set(split.cat.categories) == set(schema.SPLIT_NAMES)
    assert check_split_invariants(clean_frame, split, config) == []


def test_global_split_follows_boundaries(clean_frame: pd.DataFrame) -> None:
    split = assign_splits(clean_frame, GLOBAL)
    ts = clean_frame[schema.TIMESTAMP]
    assert (ts[split == "train"] < pd.Timestamp("2017-07-04")).all()
    assert ts[split == "val"].between(pd.Timestamp("2017-07-04"), pd.Timestamp("2017-07-06")).all()
    assert (ts[split == "test"] >= pd.Timestamp("2017-07-06")).all()
    # Validation is later than training, test later than validation.
    assert ts[split == "train"].max() < ts[split == "val"].min() < ts[split == "test"].min()


def test_global_day_split_drops_unseen_classes_from_train(clean_frame: pd.DataFrame) -> None:
    """The ADR-0008 concern, reproduced on fixtures: Thursday-only classes miss training."""
    summary = split_summary(clean_frame, assign_splits(clean_frame, GLOBAL), GLOBAL)
    assert "Web Attack - Brute Force" in summary["classes_absent_from_train"]


def test_grouped_split_gives_every_group_all_three_splits(clean_frame: pd.DataFrame) -> None:
    split = assign_splits(clean_frame, GROUPED)
    counts = class_split_counts(clean_frame, split)
    assert (counts > 0).all().all()
    summary = split_summary(clean_frame, split, GROUPED)
    assert summary["classes_absent_from_train"] == []
    assert summary["invariant_violations"] == []


def test_grouped_split_exact_fractions_with_distinct_timestamps() -> None:
    frame = _frame([f"2017-07-03 09:{m:02d}" for m in range(50)])
    split = assign_splits(frame, GROUPED)
    assert split.value_counts().to_dict() == {"train": 30, "val": 10, "test": 10}
    # The earliest 30 flows train.
    assert (split.iloc[:30] == "train").all()


def test_grouped_split_never_splits_a_timestamp_across_splits() -> None:
    # 10 flows share one timestamp around the 60% cut point.
    times = [f"2017-07-03 09:{m:02d}" for m in range(25)] + ["2017-07-03 10:00"] * 10
    times += [f"2017-07-03 11:{m:02d}" for m in range(15)]
    frame = _frame(times)
    split = assign_splits(frame, GROUPED)
    tied = split[frame[schema.TIMESTAMP] == pd.Timestamp("2017-07-03 10:00")]
    assert tied.nunique() == 1
    assert check_split_invariants(frame, split, GROUPED) == []


def test_split_is_deterministic_and_independent_of_row_order(clean_frame: pd.DataFrame) -> None:
    first = assign_splits(clean_frame, GROUPED)
    shuffled = clean_frame.sample(frac=1.0, random_state=7)
    second = assign_splits(shuffled, GROUPED)
    assert second.reindex(clean_frame.index).equals(first)


def test_invariant_check_detects_leakage() -> None:
    frame = _frame(["2017-07-03 09:00", "2017-07-03 10:00", "2017-07-03 11:00"])
    bad = pd.Series(
        pd.Categorical(["val", "train", "test"], categories=list(schema.SPLIT_NAMES)),
        index=frame.index,
    )
    problems = check_split_invariants(frame, bad, GROUPED)
    assert problems and "train" in problems[0]


def test_rows_without_timestamp_are_rejected() -> None:
    frame = _frame(["2017-07-03 09:00", "2017-07-03 10:00"])
    frame.loc[1, schema.TIMESTAMP] = pd.NaT
    with pytest.raises(ValueError, match="timestamp"):
        assign_splits(frame, GLOBAL)


def test_evaluable_classes_respect_min_support() -> None:
    times = [f"2017-07-03 09:{m:02d}" for m in range(50)]
    labels = ["BENIGN"] * 40 + ["Bot"] * 10
    frame = _frame(times, labels)
    summary = split_summary(frame, assign_splits(frame, GROUPED), GROUPED)
    # Bot has 6/2/2 flows: below min_class_support=5 in val and test.
    assert summary["evaluable_classes"] == ["BENIGN"]
    assert summary["class_counts"]["Bot"] == {"train": 6, "val": 2, "test": 2}


def test_only_chronological_strategies_exist() -> None:
    allowed = SplitConfig.model_fields["strategy"].annotation
    assert str(allowed) == "typing.Literal['global_time', 'grouped_time']"
