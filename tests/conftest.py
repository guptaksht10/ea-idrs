"""Synthetic CIC-IDS2017-style fixtures.

The fixtures use the **real column schema** from `configs/data/cicids2017.yaml` and reproduce
the raw-file quirks the cleaning code must handle: leading spaces in headers, a duplicated
`Fwd Header Length` column, `Infinity`/`NaN` strings, a non-UTF-8 dash in web-attack labels,
blank trailing rows and 12-hour afternoon timestamps. Values are random and carry no meaning:
any metric computed on them is a synthetic pipeline test, never a research result.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from eaidrs.core.config import DatasetConfig, RawFile, load_dataset_config

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_CONFIG_PATH = REPO_ROOT / "configs" / "data" / "cicids2017.yaml"
WEB_ATTACK_RAW = "Web Attack \x96 Brute Force"  # as stored in the original Thursday file


def _times(start: dt.datetime, count: int, step_minutes: int) -> list[dt.datetime]:
    return [start + dt.timedelta(minutes=step_minutes * i) for i in range(count)]


def _raw_time_text(moment: dt.datetime, with_seconds: bool) -> str:
    """Write times like the raw files: day-first date, 12-hour clock without AM/PM."""
    hour = moment.hour - 12 if moment.hour > 12 else moment.hour
    clock = f"{hour}:{moment.minute:02d}" + (f":{moment.second:02d}" if with_seconds else "")
    return f"{moment.day}/{moment.month}/{moment.year} {clock}"


def make_raw_frame(
    config: DatasetConfig,
    events: list[tuple[str, dt.datetime]],
    *,
    with_seconds: bool,
    seed: int,
) -> pd.DataFrame:
    """Build a raw-format frame (column names exactly as in the config) for (label, time) events."""
    rng = np.random.default_rng(seed)
    n = len(events)
    labels = [label for label, _ in events]
    frame = pd.DataFrame(
        {
            "Flow ID": [f"192.168.10.5-8.8.8.8-{40000 + i}-80-6" for i in range(n)],
            "Source IP": "192.168.10.5",
            "Source Port": rng.integers(1024, 65535, n),
            "Destination IP": "8.8.8.8",
            "Destination Port": rng.choice([21, 22, 80, 443], n),
            "Protocol": 6,
            "Timestamp": [_raw_time_text(moment, with_seconds) for _, moment in events],
        }
    )
    offsets = np.array([sum(map(ord, label)) % 7 for label in labels], dtype=float)
    feature_values = {
        column: rng.normal(loc=100.0 * (1 + offsets), scale=10.0).round(3)
        for column in config.feature_columns
    }
    frame = pd.concat([frame, pd.DataFrame(feature_values)], axis=1)
    frame["Fwd Header Length.1"] = frame["Fwd Header Length"]
    frame["Label"] = labels
    return frame[config.expected_raw_columns]


def write_raw_csv(frame: pd.DataFrame, path: Path, *, encoding: str, blank_rows: int = 0) -> None:
    """Write like the originals: ", "-separated header with the duplicated column name."""
    header = ", ".join(
        "Fwd Header Length" if column == "Fwd Header Length.1" else column
        for column in frame.columns
    )
    body = frame.to_csv(header=False, index=False, lineterminator="\n")
    blanks = ("," * (len(frame.columns) - 1) + "\n") * blank_rows
    path.write_bytes((header + "\n" + body + blanks).encode(encoding))


@dataclass(frozen=True)
class FixtureDataset:
    config: DatasetConfig
    raw_dir: Path
    config_path: Path
    expected_counts: dict[tuple[str, str], int]  # (day, normalised label) -> rows


@pytest.fixture(scope="session")
def base_config() -> DatasetConfig:
    return load_dataset_config(DATA_CONFIG_PATH)


@pytest.fixture(scope="session")
def fixture_dataset(
    base_config: DatasetConfig, tmp_path_factory: pytest.TempPathFactory
) -> FixtureDataset:
    """Three small raw files (Mon, Tue, Thu) written to a temporary data directory."""
    data_root = tmp_path_factory.mktemp("data")
    raw_dir = data_root / "raw" / "cicids2017"
    raw_dir.mkdir(parents=True)

    monday = dt.datetime(2017, 7, 3, 9, 0, 0)
    tuesday = dt.datetime(2017, 7, 4, 9, 0)
    thursday = dt.datetime(2017, 7, 6, 9, 0)
    files = {
        RawFile(name="Monday-WorkingHours.pcap_ISCX.csv", day="monday", date=monday.date()): (
            [("BENIGN", t) for t in _times(monday, 30, 15)],  # 09:00 .. 16:15
            True,
            0,
        ),
        RawFile(name="Tuesday-WorkingHours.pcap_ISCX.csv", day="tuesday", date=tuesday.date()): (
            [("BENIGN", t) for t in _times(tuesday, 20, 20)]
            + [("FTP-Patator", t) for t in _times(tuesday.replace(minute=20), 20, 1)]
            + [("SSH-Patator", t) for t in _times(tuesday.replace(hour=14), 20, 1)],
            False,
            0,
        ),
        RawFile(
            name="Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv",
            day="thursday",
            date=thursday.date(),
        ): (
            [("BENIGN", t) for t in _times(thursday, 20, 15)]
            + [(WEB_ATTACK_RAW, t) for t in _times(thursday.replace(minute=20), 20, 1)],
            False,
            3,
        ),
    }

    expected: dict[tuple[str, str], int] = {}
    for index, (raw_file, (events, with_seconds, blank_rows)) in enumerate(files.items()):
        frame = make_raw_frame(base_config, events, with_seconds=with_seconds, seed=index)
        if raw_file.day == "thursday":
            frame["Flow Bytes/s"] = frame["Flow Bytes/s"].astype(object)
            frame["Flow Packets/s"] = frame["Flow Packets/s"].astype(object)
            frame.loc[0, "Flow Bytes/s"] = "Infinity"
            frame.loc[1, "Flow Bytes/s"] = "NaN"
            frame.loc[2, "Flow Packets/s"] = "Infinity"
        write_raw_csv(
            frame, raw_dir / raw_file.name, encoding=base_config.encoding, blank_rows=blank_rows
        )
        for label, _ in events:
            key = (raw_file.day, label.replace("\x96", "-"))
            expected[key] = expected.get(key, 0) + 1

    config = base_config.model_copy(update={"files": list(files), "raw_dir": raw_dir})
    config_path = data_root / "cicids2017_fixture.yaml"
    config_path.write_text(yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False))
    return FixtureDataset(
        config=config, raw_dir=raw_dir, config_path=config_path, expected_counts=expected
    )
