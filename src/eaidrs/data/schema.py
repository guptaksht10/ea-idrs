"""Names of the columns that cleaning adds to every dataset, shared across the pipeline."""

from __future__ import annotations

from typing import Final, Literal

LABEL: Final = "label"
LABEL_ORIGINAL: Final = "label_original"
TIMESTAMP: Final = "timestamp"
DAY: Final = "day"
SOURCE_FILE: Final = "source_file"
SOURCE_ROW: Final = "source_row"
SPLIT: Final = "split"

BENIGN_LABEL: Final = "BENIGN"

SplitName = Literal["train", "val", "test"]
SPLIT_NAMES: Final[tuple[SplitName, ...]] = ("train", "val", "test")

# Provenance columns added by cleaning, in output order (before identifiers and features).
PROVENANCE_COLUMNS: Final = (SOURCE_FILE, SOURCE_ROW, DAY, TIMESTAMP)
