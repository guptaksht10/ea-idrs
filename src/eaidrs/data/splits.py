"""Chronological train / validation / test assignment (ADR-0008).

Two strategies, both strictly chronological:

* ``global_time``: one timeline cut at ``val_start`` and ``test_start``.
* ``grouped_time``: inside every group (default: day x label), the earliest flows train,
  then validate, then test. Cuts are placed *between distinct timestamps*, so within a group
  every training timestamp is strictly earlier than every validation timestamp, which is
  strictly earlier than every test timestamp.

Random splitting is intentionally not offered.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from eaidrs.core.config import SplitConfig, SplitFractions
from eaidrs.data import schema


def _split_one_group(timestamps: np.ndarray, fractions: SplitFractions) -> np.ndarray:
    """Assign train/val/test inside one group using timestamp cut points."""
    n = len(timestamps)
    ordered = np.sort(timestamps, kind="stable")
    first_val = int(round(n * fractions.train))
    first_test = int(round(n * (fractions.train + fractions.val)))
    in_train = timestamps < ordered[first_val] if first_val < n else np.ones(n, dtype=bool)
    in_test = timestamps >= ordered[first_test] if first_test < n else np.zeros(n, dtype=bool)
    return np.where(in_train, "train", np.where(in_test, "test", "val"))


def assign_splits(frame: pd.DataFrame, config: SplitConfig) -> pd.Series:
    """Return a categorical series (train/val/test) aligned with `frame`'s index."""
    timestamps = frame[schema.TIMESTAMP]
    if timestamps.isna().any():
        raise ValueError("cannot split rows without a timestamp; clean the data first")
    ts = timestamps.to_numpy(dtype="datetime64[ns]")

    if config.strategy == "global_time":
        assert config.val_start is not None and config.test_start is not None
        val_start = np.datetime64(config.val_start, "ns")
        test_start = np.datetime64(config.test_start, "ns")
        labels = np.where(ts < val_start, "train", np.where(ts < test_start, "val", "test"))
    else:
        assert config.fractions is not None
        missing = [column for column in config.group_by if column not in frame.columns]
        if missing:
            raise KeyError(f"group_by columns not in frame: {missing}")
        labels = np.empty(len(frame), dtype=object)
        grouped = frame.groupby(config.group_by, observed=True, sort=False)
        for positions in grouped.indices.values():
            labels[positions] = _split_one_group(ts[positions], config.fractions)

    return pd.Series(
        pd.Categorical(labels, categories=list(schema.SPLIT_NAMES)),
        index=frame.index,
        name=schema.SPLIT,
    )


def check_split_invariants(frame: pd.DataFrame, split: pd.Series, config: SplitConfig) -> list[str]:
    """Return every violation of chronological ordering. Empty list means the split is valid.

    Checked: every row is assigned, and in each group (one global group for ``global_time``)
    max(train) < min(val), max(val) < min(test) and max(train) < min(test).
    """
    problems: list[str] = []
    if split.isna().any():
        problems.append(f"{int(split.isna().sum())} rows have no split")
    data = pd.DataFrame({schema.TIMESTAMP: frame[schema.TIMESTAMP], schema.SPLIT: split})
    if config.strategy == "grouped_time":
        for column in config.group_by:
            data[column] = frame[column]
        groups: Any = data.groupby(config.group_by, observed=True, sort=False)
    else:
        groups = [("all rows", data)]

    for key, group in groups:
        by_split = group.groupby(schema.SPLIT, observed=True)[schema.TIMESTAMP]
        lows, highs = by_split.min(), by_split.max()
        for earlier, later in (("train", "val"), ("val", "test"), ("train", "test")):
            if earlier in highs.index and later in lows.index and highs[earlier] >= lows[later]:
                problems.append(
                    f"group {key}: latest {earlier} {highs[earlier]} is not before "
                    f"earliest {later} {lows[later]}"
                )
    return problems


def class_split_counts(frame: pd.DataFrame, split: pd.Series) -> pd.DataFrame:
    """Rows per label (index) and split (columns train/val/test), zeros included."""
    table = pd.crosstab(frame[schema.LABEL], split, dropna=False)
    table = table.reindex(columns=list(schema.SPLIT_NAMES), fill_value=0)
    table.columns.name = None
    return table.astype("int64")


def split_summary(frame: pd.DataFrame, split: pd.Series, config: SplitConfig) -> dict[str, Any]:
    """Machine-readable description of a split for run folders and the data card."""
    counts = class_split_counts(frame, split)
    evaluable = counts[(counts >= config.min_class_support).all(axis=1)].index.tolist()
    ranges: dict[str, dict[str, str | int | None]] = {}
    for name in schema.SPLIT_NAMES:
        ts = frame.loc[split == name, schema.TIMESTAMP]
        ranges[name] = {
            "rows": len(ts),
            "first_timestamp": None if ts.empty else str(ts.min()),
            "last_timestamp": None if ts.empty else str(ts.max()),
        }
    return {
        "split_config": config.model_dump(mode="json"),
        "splits": ranges,
        "class_counts": {
            str(label): {str(k): int(v) for k, v in row.items()} for label, row in counts.iterrows()
        },
        "classes_absent_from_train": [str(c) for c in counts.index[counts["train"] == 0]],
        "min_class_support": config.min_class_support,
        "evaluable_classes": [str(c) for c in evaluable],
        "invariant_violations": check_split_invariants(frame, split, config),
    }
