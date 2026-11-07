from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from eaidrs.core.config import DatasetConfig
from eaidrs.data import schema
from eaidrs.data.cleaning import (
    SchemaError,
    clean_raw_frame,
    normalise_column_names,
    normalise_label,
    parse_timestamps,
)
from eaidrs.data.loading import load_clean_dataset, read_raw_csv
from tests.conftest import FixtureDataset

FORMATS = ["%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("BENIGN", "BENIGN"),
        ("  DoS  Hulk ", "DoS Hulk"),
        ("Web Attack \x96 Brute Force", "Web Attack - Brute Force"),
        ("Web Attack � XSS", "Web Attack - XSS"),
        ("Web Attack – Sql Injection", "Web Attack - Sql Injection"),
        ("Web Attack - XSS", "Web Attack - XSS"),
    ],
)
def test_normalise_label(raw: str, expected: str) -> None:
    assert normalise_label(raw) == expected


def test_normalise_column_names_strips_spaces() -> None:
    assert normalise_column_names(pd.Index([" Flow ID", " Label ", "x"])) == [
        "Flow ID",
        "Label",
        "x",
    ]


def test_parse_timestamps_formats_and_afternoon_shift() -> None:
    raw = pd.Series(["4/7/2017 9:20", "4/7/2017 2:05", "3/7/2017 08:55:58", "garbage", None])
    parsed, shifted = parse_timestamps(raw, FORMATS, afternoon_hour_shift_below=8)
    assert parsed.iloc[0] == pd.Timestamp("2017-07-04 09:20")
    assert parsed.iloc[1] == pd.Timestamp("2017-07-04 14:05")  # 12-hour clock fixed
    assert parsed.iloc[2] == pd.Timestamp("2017-07-03 08:55:58")
    assert parsed.iloc[3:].isna().all()
    assert shifted == 1


def test_parse_timestamps_without_shift_keeps_hours() -> None:
    parsed, shifted = parse_timestamps(pd.Series(["4/7/2017 2:05"]), FORMATS, None)
    assert parsed.iloc[0].hour == 2
    assert shifted == 0


@pytest.fixture
def thursday_clean(fixture_dataset: FixtureDataset) -> tuple[pd.DataFrame, object]:
    config = fixture_dataset.config
    raw_file = next(f for f in config.files if f.day == "thursday")
    raw = read_raw_csv(fixture_dataset.raw_dir / raw_file.name, config.encoding)
    return clean_raw_frame(raw, config, raw_file)


def test_cleaning_handles_infinity_nan_blank_rows_and_labels(
    thursday_clean: tuple[pd.DataFrame, object],
) -> None:
    cleaned, report = thursday_clean
    assert report.rows_read == 43  # 40 flows + 3 blank rows
    assert report.blank_rows_dropped == 3
    assert report.rows_kept == 40
    assert report.infinite_values == {"Flow Bytes/s": 1, "Flow Packets/s": 1}
    # The Infinity becomes NaN, and the explicit NaN stays NaN: 2 missing in Flow Bytes/s.
    assert report.missing_values["Flow Bytes/s"] == 2
    assert not np.isinf(cleaned["Flow Bytes/s"].to_numpy(dtype="float64", na_value=np.nan)).any()
    assert set(cleaned[schema.LABEL]) == {"BENIGN", "Web Attack - Brute Force"}


def test_cleaning_output_schema(
    thursday_clean: tuple[pd.DataFrame, object], base_config: DatasetConfig
) -> None:
    cleaned, report = thursday_clean
    assert "Fwd Header Length.1" not in cleaned.columns  # identical duplicate dropped
    assert report.dropped_duplicate_columns == ["Fwd Header Length.1"]
    features = [c for c in base_config.feature_columns if c != "Fwd Header Length.1"]
    assert all(cleaned[c].dtype == np.float32 for c in features)
    assert list(cleaned.columns[:4]) == list(schema.PROVENANCE_COLUMNS)
    assert cleaned[schema.TIMESTAMP].notna().all()
    assert "Timestamp" not in cleaned.columns  # raw string replaced by parsed column


def test_differing_duplicate_column_is_kept_and_reported(fixture_dataset: FixtureDataset) -> None:
    config = fixture_dataset.config
    raw_file = config.files[0]
    raw = read_raw_csv(fixture_dataset.raw_dir / raw_file.name, config.encoding)
    raw.columns = [c.strip() for c in raw.columns]
    raw["Fwd Header Length.1"] = raw["Fwd Header Length"] + 1
    cleaned, report = clean_raw_frame(raw, config, raw_file)
    assert "Fwd Header Length.1" in cleaned.columns
    assert report.kept_differing_duplicate_columns == ["Fwd Header Length.1"]


def test_missing_required_column_raises(fixture_dataset: FixtureDataset) -> None:
    config = fixture_dataset.config
    raw_file = config.files[0]
    raw = read_raw_csv(fixture_dataset.raw_dir / raw_file.name, config.encoding)
    raw = raw.drop(columns=[c for c in raw.columns if c.strip() == "Flow Duration"])
    with pytest.raises(SchemaError, match="Flow Duration"):
        clean_raw_frame(raw, config, raw_file)


def test_unexpected_column_is_reported_and_dropped(fixture_dataset: FixtureDataset) -> None:
    config = fixture_dataset.config
    raw_file = config.files[0]
    raw = read_raw_csv(fixture_dataset.raw_dir / raw_file.name, config.encoding)
    raw["Surprise"] = 1
    cleaned, report = clean_raw_frame(raw, config, raw_file)
    assert report.unexpected_columns == ["Surprise"]
    assert "Surprise" not in cleaned.columns


def test_label_groups_keep_original_label(fixture_dataset: FixtureDataset) -> None:
    config = fixture_dataset.config.model_copy(
        update={"label_groups": {"FTP-Patator": "Patator", "SSH-Patator": "Patator"}}
    )
    dataset = load_clean_dataset(config, fixture_dataset.raw_dir)
    patator = dataset.frame[dataset.frame[schema.LABEL] == "Patator"]
    assert len(patator) == 40
    assert set(patator[schema.LABEL_ORIGINAL]) == {"FTP-Patator", "SSH-Patator"}


def test_loaded_dataset_is_sorted_and_complete(fixture_dataset: FixtureDataset) -> None:
    dataset = load_clean_dataset(fixture_dataset.config, fixture_dataset.raw_dir)
    frame = dataset.frame
    assert frame[schema.TIMESTAMP].is_monotonic_increasing
    counts = frame.groupby([schema.DAY, schema.LABEL], observed=True).size()
    assert {(str(d), str(lbl)): int(n) for (d, lbl), n in counts.items()} == (
        fixture_dataset.expected_counts
    )
    # Afternoon flows written as "2:00" must land at 14:00, not 02:00.
    ssh = frame.loc[frame[schema.LABEL] == "SSH-Patator", schema.TIMESTAMP]
    assert (ssh.dt.hour == 14).all()
    assert "Fwd Header Length.1" not in dataset.feature_columns


def test_missing_raw_file_gives_helpful_error(
    fixture_dataset: FixtureDataset, tmp_path: Path
) -> None:
    with pytest.raises(FileNotFoundError, match="data/README.md"):
        load_clean_dataset(fixture_dataset.config, tmp_path)
