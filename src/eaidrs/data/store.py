"""Write and read processed split files, keeping the test split sealed (ADR-0004).

Layout: ``<data_dir>/processed/<dataset>/<split_config_name>/{train,val}.parquet`` and
``.../sealed/test.parquet``. Reading the test split requires ``allow_sealed_test=True``, which
only the approved final test protocol should pass.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from eaidrs.core.paths import data_dir
from eaidrs.data import schema
from eaidrs.data.schema import SplitName

SEALED_DIR = "sealed"


class SealedSplitError(PermissionError):
    """Raised when code tries to read the sealed test split without explicit permission."""


def processed_dir(dataset_name: str, split_name: str) -> Path:
    return data_dir() / "processed" / dataset_name / split_name


def split_file(out_dir: Path, which: SplitName) -> Path:
    if which == "test":
        return out_dir / SEALED_DIR / "test.parquet"
    return out_dir / f"{which}.parquet"


def write_splits(frame: pd.DataFrame, split: pd.Series, out_dir: Path) -> dict[str, Path]:
    """Write one parquet file per split and return their paths."""
    written: dict[str, Path] = {}
    for which in schema.SPLIT_NAMES:
        path = split_file(out_dir, which)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.loc[split == which].reset_index(drop=True).to_parquet(path, index=False)
        written[which] = path
    return written


def read_split(out_dir: Path, which: SplitName, *, allow_sealed_test: bool = False) -> pd.DataFrame:
    """Read a processed split. The test split is refused unless explicitly allowed."""
    if which == "test" and not allow_sealed_test:
        raise SealedSplitError(
            "the test split is sealed until the test protocol is approved "
            "(pass allow_sealed_test=True only in the approved final evaluation)"
        )
    return pd.read_parquet(split_file(out_dir, which))
