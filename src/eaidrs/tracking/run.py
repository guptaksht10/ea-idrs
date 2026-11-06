"""Tracked run folders (blueprint §6.12).

``with tracked_run("audit", configs={...}) as run:`` creates
``runs/<UTC timestamp>_<name>_<short git sha>/`` containing:

* ``config/``          exact copies of the config files used
* ``git_commit.txt``   commit hash, dirty flag and ``git status --porcelain``
* ``environment.txt``  Python, platform and every installed package version
* ``run.json``         name, status (running/completed/failed), times, seed, data manifest hash
* ``metrics.json``     whatever the run stores in ``run.metrics``

Failed runs keep their folder with ``status: failed`` and the error, so failures are recorded
rather than silently lost.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

import pandas as pd

from eaidrs.core.paths import manifest_path, repo_root, runs_dir
from eaidrs.data.manifest import manifest_digest


@dataclass(frozen=True)
class GitState:
    commit: str
    dirty: bool
    status: str

    @property
    def short(self) -> str:
        return self.commit[:7] if self.commit != "unknown" else "nogit"


def git_state(cwd: Path | None = None) -> GitState:
    """Current commit and working-tree state, or ``unknown`` outside a git checkout."""
    where = cwd or repo_root()
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=where, capture_output=True, text=True, check=True
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=where, capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return GitState(commit="unknown", dirty=True, status="")
    return GitState(commit=commit, dirty=bool(status.strip()), status=status)


def environment_report() -> str:
    """Interpreter, OS, CPU and a sorted ``name==version`` list of installed distributions."""
    packages = sorted(
        {f"{d.metadata['Name']}=={d.version}" for d in metadata.distributions()},
        key=str.lower,
    )
    lines = [
        f"python: {sys.version.split()[0]} ({sys.executable})",
        f"platform: {platform.platform()}",
        f"machine: {platform.machine()}",
        f"processor: {platform.processor() or 'unknown'}",
        "",
        "packages:",
        *packages,
    ]
    return "\n".join(lines) + "\n"


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, pd.Timestamp | datetime):
        return value.isoformat()
    if hasattr(value, "item"):  # numpy scalars
        return value.item()
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, default=_json_default) + "\n", encoding="utf-8")


@dataclass
class Run:
    """Handle to an open run folder."""

    run_id: str
    path: Path
    metrics: dict[str, Any] = field(default_factory=dict)

    def save_json(self, name: str, payload: Any) -> Path:
        target = self.path / name
        write_json(target, payload)
        return target

    def save_table(self, name: str, table: pd.DataFrame, index: bool = True) -> Path:
        target = self.path / name
        table.to_csv(target, index=index)
        return target

    def save_text(self, name: str, text: str) -> Path:
        target = self.path / name
        target.write_text(text, encoding="utf-8")
        return target


def _new_run_dir(root: Path, name: str, short_sha: str) -> tuple[str, Path]:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = f"{stamp}_{name}_{short_sha}"
    run_id, suffix = base, 1
    while (root / run_id).exists():
        suffix += 1
        run_id = f"{base}-{suffix}"
    path = root / run_id
    path.mkdir(parents=True)
    return run_id, path


@contextmanager
def tracked_run(
    name: str,
    *,
    configs: Mapping[str, Path] | None = None,
    seed: int | None = None,
    params: Mapping[str, Any] | None = None,
    root: Path | None = None,
) -> Iterator[Run]:
    """Create a run folder, record provenance, and mark the run completed or failed."""
    git = git_state()
    run_id, path = _new_run_dir(root or runs_dir(), name, git.short)
    run = Run(run_id=run_id, path=path)

    config_copies: dict[str, str] = {}
    if configs:
        (path / "config").mkdir()
        for key, source in configs.items():
            target = path / "config" / f"{key}{source.suffix}"
            shutil.copyfile(source, target)
            config_copies[key] = source.as_posix()

    (path / "git_commit.txt").write_text(
        f"commit: {git.commit}\ndirty: {git.dirty}\n\n{git.status}", encoding="utf-8"
    )
    (path / "environment.txt").write_text(environment_report(), encoding="utf-8")

    manifest = manifest_path()
    record: dict[str, Any] = {
        "run_id": run_id,
        "name": name,
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "git_commit": git.commit,
        "git_dirty": git.dirty,
        "seed": seed,
        "params": dict(params or {}),
        "configs": config_copies,
        "data_manifest": manifest.as_posix(),
        "data_manifest_sha256": manifest_digest(manifest),
    }
    write_json(path / "run.json", record)

    started = time.perf_counter()
    try:
        yield run
        record["status"] = "completed"
    except BaseException as error:
        record["status"] = "failed"
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        record["finished_at"] = datetime.now(UTC).isoformat()
        record["duration_seconds"] = round(time.perf_counter() - started, 3)
        write_json(path / "run.json", record)
        if run.metrics:
            write_json(path / "metrics.json", run.metrics)
