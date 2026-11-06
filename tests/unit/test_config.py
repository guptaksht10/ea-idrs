from __future__ import annotations

import pytest
from pydantic import ValidationError

from eaidrs.core.config import DatasetConfig, SplitConfig, load_split_config
from tests.conftest import REPO_ROOT


def test_real_dataset_config_matches_cicids2017_schema(base_config: DatasetConfig) -> None:
    assert len(base_config.files) == 8
    assert len(base_config.feature_columns) == 77
    assert base_config.day_order == ["monday", "tuesday", "wednesday", "thursday", "friday"]
    # Identifiers must never double as features (shortcut / leakage risk).
    assert not set(base_config.identifier_columns) & set(base_config.feature_columns)


@pytest.mark.parametrize("name", ["global_by_day", "grouped_by_day_label"])
def test_split_configs_load(name: str) -> None:
    config = load_split_config(REPO_ROOT / "configs" / "split" / f"{name}.yaml")
    assert config.name == name


def test_unknown_key_is_rejected(base_config: DatasetConfig) -> None:
    payload = base_config.model_dump()
    payload["feature_colums"] = []  # typo
    with pytest.raises(ValidationError, match="feature_colums"):
        DatasetConfig.model_validate(payload)


def test_column_in_two_groups_is_rejected(base_config: DatasetConfig) -> None:
    payload = base_config.model_dump()
    payload["identifier_columns"] = [*payload["identifier_columns"], "Flow Duration"]
    with pytest.raises(ValidationError, match="Flow Duration"):
        DatasetConfig.model_validate(payload)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"name": "x", "strategy": "global_time"}, "val_start"),
        (
            {
                "name": "x",
                "strategy": "global_time",
                "val_start": "2017-07-07T00:00",
                "test_start": "2017-07-06T00:00",
            },
            "earlier",
        ),
        ({"name": "x", "strategy": "grouped_time"}, "fractions"),
        (
            {
                "name": "x",
                "strategy": "grouped_time",
                "fractions": {"train": 0.6, "val": 0.3, "test": 0.3},
            },
            "sum to 1",
        ),
        ({"name": "x", "strategy": "random"}, "strategy"),
    ],
)
def test_invalid_split_configs_are_rejected(payload: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        SplitConfig.model_validate(payload)
