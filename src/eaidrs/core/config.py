"""Pydantic models for the YAML configuration files in `configs/` (ADR-0005).

Every model forbids unknown keys, so a typo in a config fails immediately instead of
silently falling back to a default.
"""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path
from typing import Literal, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from eaidrs.core.paths import resolve_from_root


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RawFile(_StrictModel):
    """One raw CSV file and the capture day it belongs to."""

    name: str
    day: str
    date: dt.date


class DatasetConfig(_StrictModel):
    """Describes how to read and clean one raw dataset (e.g. `configs/data/cicids2017.yaml`)."""

    name: str
    version: str
    raw_dir: Path = Field(description="Relative to the data directory unless absolute.")
    encoding: str = "utf-8"
    files: list[RawFile] = Field(min_length=1)
    label_column: str
    timestamp_column: str
    timestamp_formats: list[str] = Field(min_length=1)
    afternoon_hour_shift_below: int | None = Field(default=None, ge=1, le=12)
    identifier_columns: list[str] = Field(default_factory=list)
    numeric_identifier_columns: list[str] = Field(default_factory=list)
    feature_columns: list[str] = Field(min_length=1)
    duplicate_columns: list[tuple[str, str]] = Field(default_factory=list)
    label_groups: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_columns(self) -> DatasetConfig:
        names = [f.name for f in self.files]
        if len(names) != len(set(names)):
            raise ValueError("files: duplicate file names")
        groups = {
            "identifier_columns": self.identifier_columns,
            "feature_columns": self.feature_columns,
            "label/timestamp": [self.label_column, self.timestamp_column],
        }
        seen: dict[str, str] = {}
        for group, columns in groups.items():
            for column in columns:
                if column in seen:
                    raise ValueError(f"column {column!r} listed in both {seen[column]} and {group}")
                seen[column] = group
        unknown_numeric = set(self.numeric_identifier_columns) - set(self.identifier_columns)
        if unknown_numeric:
            raise ValueError(f"numeric_identifier_columns not in identifiers: {unknown_numeric}")
        for duplicate, original in self.duplicate_columns:
            if duplicate not in self.feature_columns or original not in self.feature_columns:
                raise ValueError(
                    f"duplicate pair ({duplicate}, {original}) must be feature columns"
                )
        return self

    @property
    def expected_raw_columns(self) -> list[str]:
        """All columns a raw file must contain, after whitespace stripping."""
        return [
            *self.identifier_columns,
            self.timestamp_column,
            *self.feature_columns,
            self.label_column,
        ]

    @property
    def day_order(self) -> list[str]:
        """Capture days in chronological order, without repeats."""
        return list(dict.fromkeys(f.day for f in self.files))


class SplitFractions(_StrictModel):
    train: float = Field(gt=0, lt=1)
    val: float = Field(gt=0, lt=1)
    test: float = Field(gt=0, lt=1)

    @model_validator(mode="after")
    def _sum_to_one(self) -> SplitFractions:
        total = self.train + self.val + self.test
        if not math.isclose(total, 1.0, abs_tol=1e-9):
            raise ValueError(f"fractions must sum to 1, got {total}")
        return self


class SplitConfig(_StrictModel):
    """Chronological split definition (ADR-0008)."""

    name: str
    strategy: Literal["global_time", "grouped_time"]
    val_start: dt.datetime | None = None
    test_start: dt.datetime | None = None
    group_by: list[str] = Field(default_factory=lambda: ["day", "label"])
    fractions: SplitFractions | None = None
    min_class_support: int = Field(default=30, ge=1)

    @model_validator(mode="after")
    def _check_strategy(self) -> SplitConfig:
        if self.strategy == "global_time":
            if self.val_start is None or self.test_start is None:
                raise ValueError("global_time needs val_start and test_start")
            if self.val_start >= self.test_start:
                raise ValueError("val_start must be earlier than test_start")
        else:
            if self.fractions is None:
                raise ValueError("grouped_time needs fractions")
            if not self.group_by:
                raise ValueError("grouped_time needs at least one group_by column")
        return self


_ModelT = TypeVar("_ModelT", bound=BaseModel)


def load_yaml_model(path: str | Path, model: type[_ModelT]) -> _ModelT:
    """Load a YAML file (relative paths resolve from the repo root) into a pydantic model."""
    resolved = resolve_from_root(path)
    with resolved.open(encoding="utf-8") as handle:
        content = yaml.safe_load(handle)
    if not isinstance(content, dict):
        raise ValueError(f"{resolved}: expected a mapping at the top level")
    return model.model_validate(content)


def load_dataset_config(path: str | Path) -> DatasetConfig:
    return load_yaml_model(path, DatasetConfig)


def load_split_config(path: str | Path) -> SplitConfig:
    return load_yaml_model(path, SplitConfig)
