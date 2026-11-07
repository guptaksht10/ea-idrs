"""Read every raw file of a dataset, clean it, and return one chronologically sorted frame."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from eaidrs.core.config import DatasetConfig
from eaidrs.core.paths import data_dir
from eaidrs.data import schema
from eaidrs.data.cleaning import CleaningReport, clean_raw_frame

logger = logging.getLogger(__name__)


@dataclass
class CleanDataset:
    """The cleaned dataset plus one cleaning report per raw file."""

    frame: pd.DataFrame
    reports: list[CleaningReport]
    config: DatasetConfig

    @property
    def feature_columns(self) -> list[str]:
        """Configured feature columns that survived cleaning (duplicates may be dropped)."""
        return [c for c in self.config.feature_columns if c in self.frame.columns]


def raw_dir_for(config: DatasetConfig) -> Path:
    """Absolute raw-data directory: `raw_dir` if absolute, else relative to the data directory."""
    return config.raw_dir if config.raw_dir.is_absolute() else data_dir() / config.raw_dir


def read_raw_csv(path: Path, encoding: str) -> pd.DataFrame:
    """Read one raw CSV exactly as stored (type inference only, no cleaning)."""
    return pd.read_csv(path, encoding=encoding, low_memory=False)


def load_clean_dataset(config: DatasetConfig, raw_dir: Path | None = None) -> CleanDataset:
    """Load and clean all configured files, then sort flows by timestamp.

    Ties are broken by file order and then row order, so the result is deterministic.
    """
    directory = raw_dir if raw_dir is not None else raw_dir_for(config)
    missing = [f.name for f in config.files if not (directory / f.name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"raw files missing in {directory}: {missing}. See data/README.md for download steps."
        )

    frames: list[pd.DataFrame] = []
    reports: list[CleaningReport] = []
    for raw_file in config.files:
        logger.info("reading %s", raw_file.name)
        raw = read_raw_csv(directory / raw_file.name, config.encoding)
        cleaned, report = clean_raw_frame(raw, config, raw_file)
        del raw
        logger.info("  kept %d of %d rows", report.rows_kept, report.rows_read)
        frames.append(cleaned)
        reports.append(report)

    frame = pd.concat(frames, ignore_index=True)
    file_order = {f.name: index for index, f in enumerate(config.files)}
    frame["_file_order"] = frame[schema.SOURCE_FILE].map(file_order)
    frame = frame.sort_values(
        [schema.TIMESTAMP, "_file_order", schema.SOURCE_ROW], kind="stable"
    ).drop(columns="_file_order")
    frame[schema.SOURCE_FILE] = pd.Categorical(
        frame[schema.SOURCE_FILE], categories=[f.name for f in config.files]
    )
    frame[schema.DAY] = pd.Categorical(frame[schema.DAY], categories=config.day_order)
    return CleanDataset(frame=frame.reset_index(drop=True), reports=reports, config=config)
