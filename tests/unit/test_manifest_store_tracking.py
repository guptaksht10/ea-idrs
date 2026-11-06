"""Data integrity (manifest), sealed test split, and run-folder provenance."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from eaidrs.data import schema
from eaidrs.data.manifest import (
    build_manifest,
    manifest_digest,
    read_manifest,
    verify_manifest,
    write_manifest,
)
from eaidrs.data.store import SealedSplitError, read_split, write_splits
from eaidrs.tracking.run import tracked_run


@pytest.fixture
def manifest_setup(tmp_path: Path) -> tuple[Path, Path]:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "a.csv").write_bytes(b"x,y\n1,2\n")
    (raw / "b.csv").write_bytes(b"x,y\n3,4\n")
    manifest = tmp_path / "MANIFEST.sha256"
    write_manifest(build_manifest(tmp_path, sorted(raw.iterdir())), manifest)
    return tmp_path, manifest


def test_manifest_round_trip_verifies(manifest_setup: tuple[Path, Path]) -> None:
    base, manifest = manifest_setup
    assert set(read_manifest(manifest)) == {"raw/a.csv", "raw/b.csv"}
    assert verify_manifest(manifest, base) == []


def test_manifest_detects_modified_and_missing_files(manifest_setup: tuple[Path, Path]) -> None:
    base, manifest = manifest_setup
    before = manifest_digest(manifest)
    (base / "raw" / "a.csv").write_bytes(b"x,y\n1,999\n")
    (base / "raw" / "b.csv").unlink()
    assert sorted(verify_manifest(manifest, base)) == [
        "hash mismatch: raw/a.csv",
        "missing: raw/b.csv",
    ]
    assert manifest_digest(manifest) == before  # the manifest itself did not change


def test_manifest_rejects_malformed_line(tmp_path: Path) -> None:
    manifest = tmp_path / "MANIFEST.sha256"
    manifest.write_text("not-a-hash raw/a.csv\n")
    with pytest.raises(ValueError, match="malformed"):
        read_manifest(manifest)


def test_test_split_is_sealed(tmp_path: Path) -> None:
    frame = pd.DataFrame({"x": [1, 2, 3]})
    split = pd.Series(["train", "val", "test"], name=schema.SPLIT)
    written = write_splits(frame, split, tmp_path)
    assert written["test"].parent.name == "sealed"
    assert read_split(tmp_path, "train")["x"].tolist() == [1]
    with pytest.raises(SealedSplitError):
        read_split(tmp_path, "test")
    assert read_split(tmp_path, "test", allow_sealed_test=True)["x"].tolist() == [3]


def test_tracked_run_records_provenance(tmp_path: Path) -> None:
    config = tmp_path / "exp.yaml"
    config.write_text("seed: 1\n")
    with tracked_run("unit", configs={"exp": config}, seed=1, root=tmp_path / "runs") as run:
        run.metrics = {"value": 1.5}
    record = json.loads((run.path / "run.json").read_text())
    assert record["status"] == "completed"
    assert record["seed"] == 1
    assert len(record["git_commit"]) in (40, 7)  # full sha, or "unknown" outside git
    assert (run.path / "config" / "exp.yaml").read_text() == "seed: 1\n"
    assert (run.path / "git_commit.txt").is_file()
    assert "pandas==" in (run.path / "environment.txt").read_text()
    assert json.loads((run.path / "metrics.json").read_text()) == {"value": 1.5}


def test_failed_run_is_recorded_not_lost(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError), tracked_run("boom", root=tmp_path) as run:
        raise RuntimeError("disk full")
    record = json.loads((run.path / "run.json").read_text())
    assert record["status"] == "failed"
    assert "disk full" in record["error"]
