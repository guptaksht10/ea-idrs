"""End-to-end CLI run on the synthetic fixture: manifest -> audit -> prepare."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from eaidrs.cli import main
from eaidrs.data.store import SealedSplitError, read_split
from tests.conftest import REPO_ROOT, FixtureDataset

GROUPED = str(REPO_ROOT / "configs" / "split" / "grouped_by_day_label.yaml")
GLOBAL = str(REPO_ROOT / "configs" / "split" / "global_by_day.yaml")


@pytest.fixture
def workspace(
    fixture_dataset: FixtureDataset, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Isolated data and runs directories so tests never touch the real repo folders."""
    data = tmp_path / "data"
    shutil.copytree(fixture_dataset.raw_dir, data / "raw" / "cicids2017")
    config = fixture_dataset.config.model_copy(update={"raw_dir": Path("raw/cicids2017")})
    config_path = tmp_path / "cicids2017.yaml"
    config_path.write_text(yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False))
    monkeypatch.setenv("EAIDRS_DATA_DIR", str(data))
    monkeypatch.setenv("EAIDRS_RUNS_DIR", str(tmp_path / "runs"))
    return config_path


def _only_run(runs: Path, prefix: str) -> Path:
    matches = [p for p in runs.iterdir() if f"_{prefix}" in p.name]
    assert len(matches) == 1, matches
    return matches[0]


def test_full_data_pipeline(workspace: Path, tmp_path: Path) -> None:
    config = str(workspace)
    assert main(["manifest", "create", "--data-config", config]) == 0
    assert main(["manifest", "verify", "--data-config", config]) == 0
    assert main(["manifest", "create", "--data-config", config]) == 1  # refuses to overwrite

    assert main(["audit", "--data-config", config, "--split-config", GROUPED,
                 "--split-config", GLOBAL]) == 0  # fmt: skip
    audit_run = _only_run(tmp_path / "runs", "audit")
    record = json.loads((audit_run / "run.json").read_text())
    assert record["status"] == "completed"
    assert record["data_manifest_sha256"] is not None
    report = (audit_run / "audit_report.md").read_text(encoding="utf-8")
    assert "## Class by day" in report
    metrics = json.loads((audit_run / "metrics.json").read_text())
    assert metrics["splits"]["grouped_by_day_label"]["invariant_violations"] == 0
    assert (
        "Web Attack - Brute Force"
        in (metrics["splits"]["global_by_day"]["classes_absent_from_train"])
    )

    assert main(["prepare", "--data-config", config, "--split-config", GROUPED]) == 0
    out_dir = tmp_path / "data" / "processed" / "cicids2017" / "grouped_by_day_label"
    train = read_split(out_dir, "train")
    val = read_split(out_dir, "val")
    assert train["timestamp"].notna().all()
    assert len(train) > len(val) > 0
    with pytest.raises(SealedSplitError):
        read_split(out_dir, "test")
    summary = json.loads((out_dir / "split_summary.json").read_text())
    assert summary["invariant_violations"] == []


def test_prepare_refuses_unverified_data(workspace: Path) -> None:
    assert main(["prepare", "--data-config", str(workspace)]) == 1


def test_tampered_data_fails_audit(workspace: Path, tmp_path: Path) -> None:
    config = str(workspace)
    assert main(["manifest", "create", "--data-config", config]) == 0
    raw_file = next((tmp_path / "data" / "raw" / "cicids2017").iterdir())
    raw_file.write_bytes(raw_file.read_bytes() + b"\n")
    assert main(["audit", "--data-config", config]) == 1
