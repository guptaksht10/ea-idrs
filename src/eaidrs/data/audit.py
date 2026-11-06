"""Dataset audit tables: inventory, data quality, class-by-day, class time ranges, splits.

Every table here is computed from the cleaned data and written into a run folder. The data
card copies numbers from those files; nothing is typed in by hand.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from eaidrs.data import schema
from eaidrs.data.cleaning import CleaningReport
from eaidrs.data.loading import CleanDataset


def file_inventory(dataset: CleanDataset, file_sizes: dict[str, int]) -> pd.DataFrame:
    """One row per raw file: day, size, rows read/kept, dropped rows, time range."""
    frame = dataset.frame
    rows = []
    for raw_file, report in zip(dataset.config.files, dataset.reports, strict=True):
        ts = frame.loc[frame[schema.SOURCE_FILE] == raw_file.name, schema.TIMESTAMP]
        rows.append(
            {
                "file": raw_file.name,
                "day": raw_file.day,
                "size_bytes": file_sizes.get(raw_file.name),
                "rows_read": report.rows_read,
                "rows_kept": report.rows_kept,
                "blank_rows_dropped": report.blank_rows_dropped,
                "unparsed_timestamps_dropped": report.unparsed_timestamp_rows_dropped,
                "afternoon_shifted_rows": report.afternoon_shifted_rows,
                "first_timestamp": ts.min() if not ts.empty else pd.NaT,
                "last_timestamp": ts.max() if not ts.empty else pd.NaT,
            }
        )
    return pd.DataFrame(rows)


def quality_table(
    reports: Sequence[CleaningReport], feature_columns: Sequence[str]
) -> pd.DataFrame:
    """Per-feature totals across files: non-numeric, infinite, missing, negative values.

    Only features with at least one issue are returned.
    """
    issues = ("non_numeric", "infinite", "missing_after_cleaning", "negative")
    totals = {column: dict.fromkeys(issues, 0) for column in feature_columns}
    for report in reports:
        per_issue = (
            report.non_numeric_values,
            report.infinite_values,
            report.missing_values,
            report.negative_values,
        )
        for issue, counts in zip(issues, per_issue, strict=True):
            for column, count in counts.items():
                if column in totals:
                    totals[column][issue] += count
    table = pd.DataFrame.from_dict(totals, orient="index", columns=list(issues)).astype("int64")
    table.index.name = "column"
    return table[(table != 0).any(axis=1)]


def constant_columns(frame: pd.DataFrame, feature_columns: Sequence[str]) -> list[str]:
    """Features with at most one distinct non-missing value in the whole dataset.

    Informational only: the feature pipeline decides removal on the training split.
    """
    return [c for c in feature_columns if frame[c].nunique(dropna=True) <= 1]


def class_by_day(frame: pd.DataFrame, day_order: Sequence[str]) -> pd.DataFrame:
    """Flow counts per label (rows) and capture day (columns), with totals."""
    table = pd.crosstab(frame[schema.LABEL], frame[schema.DAY], dropna=False)
    table = table.reindex(columns=list(day_order), fill_value=0)
    table.columns.name = None
    table["total"] = table.sum(axis=1)
    table = table.sort_values("total", ascending=False)
    table.loc["TOTAL"] = table.sum(axis=0)
    return table.astype("int64")


def class_time_ranges(frame: pd.DataFrame) -> pd.DataFrame:
    """First/last timestamp and count for each (day, label): the attack episodes."""
    grouped = frame.groupby([schema.DAY, schema.LABEL], observed=True)[schema.TIMESTAMP]
    table = grouped.agg(flows="size", first_timestamp="min", last_timestamp="max")
    return table.reset_index().sort_values([schema.DAY, "first_timestamp"])


def duplicate_row_count(frame: pd.DataFrame, columns: Sequence[str]) -> int:
    """Rows that exactly repeat an earlier row on `columns` (features + label)."""
    return int(frame.duplicated(subset=list(columns)).sum())


def cross_split_duplicates(
    frame: pd.DataFrame, split: pd.Series, columns: Sequence[str]
) -> dict[str, int]:
    """Validation/test rows whose `columns` values also occur in the training split.

    A high count means near-identical flows sit on both sides of the split, which can inflate
    validation metrics. Reported, not removed (decision DATA-08).
    """
    hashes = pd.util.hash_pandas_object(frame[list(columns)], index=False)
    train_hashes = set(hashes[split == "train"].to_numpy().tolist())
    return {
        which: int(hashes[split == which].isin(train_hashes).sum()) for which in ("val", "test")
    }


def markdown_table(table: pd.DataFrame, index: bool = True) -> str:
    """Render a DataFrame as a GitHub Markdown table without extra dependencies."""
    shown = table.reset_index() if index else table
    header = [str(c) for c in shown.columns]
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
    ]
    for row in shown.itertuples(index=False):
        lines.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |")
    return "\n".join(lines)
