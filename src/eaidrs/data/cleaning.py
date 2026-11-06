"""Deterministic, per-file cleaning of raw CIC-IDS2017-style flow records.

Cleaning fits nothing: no statistic computed from the data is reused later. Anything that
learns from data (constant-column removal, scaling) belongs in the feature pipeline and is
fitted on the training split only.

Missing and infinite values are deliberately *not* imputed. Infinity becomes NaN and
gradient-boosted trees route NaN natively, which avoids fitting an imputer at all.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from eaidrs.core.config import DatasetConfig, RawFile
from eaidrs.data import schema


class SchemaError(ValueError):
    """A raw file does not contain the columns the dataset config requires."""


# "Web Attack <dash> Brute Force": the dash is a non-UTF-8 byte in the original files and
# decodes differently depending on encoding (\x96, U+FFFD, en dash). Normalise all to " - ".
_WEB_ATTACK_PREFIX = re.compile(r"^Web Attack\W+")


@dataclass
class CleaningReport:
    """What cleaning found and changed in one raw file. Feeds the audit and data card."""

    source_file: str
    rows_read: int
    rows_kept: int = 0
    blank_rows_dropped: int = 0
    unparsed_timestamp_rows_dropped: int = 0
    afternoon_shifted_rows: int = 0
    unexpected_columns: list[str] = field(default_factory=list)
    non_numeric_values: dict[str, int] = field(default_factory=dict)
    infinite_values: dict[str, int] = field(default_factory=dict)
    missing_values: dict[str, int] = field(default_factory=dict)
    negative_values: dict[str, int] = field(default_factory=dict)
    dropped_duplicate_columns: list[str] = field(default_factory=list)
    kept_differing_duplicate_columns: list[str] = field(default_factory=list)
    label_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalise_column_names(columns: pd.Index) -> list[str]:
    """Strip surrounding whitespace (raw headers have leading spaces)."""
    return [str(column).strip() for column in columns]


def normalise_label(raw: object) -> str:
    """Collapse whitespace and unify the web-attack separator to ``"Web Attack - <type>"``."""
    label = " ".join(str(raw).split())
    return _WEB_ATTACK_PREFIX.sub("Web Attack - ", label)


def parse_timestamps(
    values: pd.Series,
    formats: list[str],
    afternoon_hour_shift_below: int | None,
) -> tuple[pd.Series, int]:
    """Parse timestamp strings by trying each explicit format in order.

    Returns the parsed series (NaT where nothing matched) and the number of values moved
    into the afternoon. Explicit formats are used instead of dateutil guessing because they
    are fast on millions of rows and never silently swap day and month.
    """
    text = values.astype("string").str.strip()
    parsed = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    for fmt in formats:
        todo = parsed.isna()
        if not todo.any():
            break
        parsed.loc[todo] = pd.to_datetime(text[todo], format=fmt, errors="coerce")
    shifted = 0
    if afternoon_hour_shift_below is not None:
        needs_shift = parsed.notna() & (parsed.dt.hour < afternoon_hour_shift_below)
        shifted = int(needs_shift.sum())
        parsed.loc[needs_shift] = parsed[needs_shift] + pd.Timedelta(hours=12)
    return parsed, shifted


def _to_numeric(column: pd.Series) -> tuple[pd.Series, int]:
    """Coerce to float64, returning how many non-empty values were not numbers."""
    numeric = pd.to_numeric(column, errors="coerce")
    non_numeric = int((column.notna() & numeric.isna()).sum())
    return numeric.astype("float64"), non_numeric


def clean_raw_frame(
    raw: pd.DataFrame, config: DatasetConfig, raw_file: RawFile
) -> tuple[pd.DataFrame, CleaningReport]:
    """Clean one raw file. Returns provenance + identifier + feature + label columns.

    Raises:
        SchemaError: if a configured identifier, timestamp, feature or label column is missing.
    """
    report = CleaningReport(source_file=raw_file.name, rows_read=len(raw))
    frame = raw.copy()
    frame.columns = pd.Index(normalise_column_names(frame.columns))
    frame[schema.SOURCE_ROW] = np.arange(len(frame), dtype=np.int64)

    expected = config.expected_raw_columns
    missing = [column for column in expected if column not in frame.columns]
    if missing:
        raise SchemaError(f"{raw_file.name}: missing columns {missing}")
    report.unexpected_columns = [
        column for column in frame.columns if column not in expected and column != schema.SOURCE_ROW
    ]

    # Blank rows (no label) occur at the end of some raw files.
    labels = frame[config.label_column]
    blank = labels.isna() | (labels.astype("string").str.strip() == "")
    report.blank_rows_dropped = int(blank.sum())
    frame = frame.loc[~blank]

    timestamps, report.afternoon_shifted_rows = parse_timestamps(
        frame[config.timestamp_column],
        config.timestamp_formats,
        config.afternoon_hour_shift_below,
    )
    unparsed = timestamps.isna()
    report.unparsed_timestamp_rows_dropped = int(unparsed.sum())
    frame = frame.loc[~unparsed]
    timestamps = timestamps.loc[~unparsed]

    out = pd.DataFrame(index=frame.index)
    out[schema.SOURCE_FILE] = raw_file.name
    out[schema.SOURCE_ROW] = frame[schema.SOURCE_ROW]
    out[schema.DAY] = raw_file.day
    out[schema.TIMESTAMP] = timestamps

    for column in config.identifier_columns:
        if column in config.numeric_identifier_columns:
            numeric, bad = _to_numeric(frame[column])
            if bad:
                report.non_numeric_values[column] = bad
            # Ports/protocol are integers; keep floats only if the file says otherwise.
            integral = bool((numeric.dropna() % 1 == 0).all())
            out[column] = numeric.astype("Int64") if integral else numeric
        else:
            out[column] = frame[column].astype("string").str.strip()

    features: dict[str, pd.Series] = {}
    for column in config.feature_columns:
        numeric, bad = _to_numeric(frame[column])
        infinite = np.isinf(numeric.to_numpy())
        if bad:
            report.non_numeric_values[column] = bad
        if infinite.any():
            report.infinite_values[column] = int(infinite.sum())
            numeric = numeric.mask(infinite)
        negative = int((numeric < 0).sum())
        if negative:
            report.negative_values[column] = negative
        missing_count = int(numeric.isna().sum())
        if missing_count:
            report.missing_values[column] = missing_count
        features[column] = numeric

    for duplicate, original in config.duplicate_columns:
        if features[duplicate].equals(features[original]):
            del features[duplicate]
            report.dropped_duplicate_columns.append(duplicate)
        else:
            report.kept_differing_duplicate_columns.append(duplicate)

    # float32 halves memory; the precision loss is irrelevant for tree split thresholds.
    feature_frame = pd.DataFrame(features, index=frame.index).astype("float32")
    out = pd.concat([out, feature_frame], axis=1)

    fine_labels = frame[config.label_column].map(normalise_label).astype("string")
    if config.label_groups:
        out[schema.LABEL_ORIGINAL] = fine_labels
        out[schema.LABEL] = fine_labels.replace(config.label_groups)
    else:
        out[schema.LABEL] = fine_labels

    report.rows_kept = len(out)
    report.label_counts = {
        str(label): int(count) for label, count in out[schema.LABEL].value_counts().items()
    }
    return out.reset_index(drop=True), report
