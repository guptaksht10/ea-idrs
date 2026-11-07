"""Resolve repository, data, run and artifact directories.

Each directory can be overridden by an environment variable (documented in `.env.example`),
which lets the dataset live on another drive and lets tests write into temporary folders.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT_ENV = "EAIDRS_ROOT"
DATA_DIR_ENV = "EAIDRS_DATA_DIR"
RUNS_DIR_ENV = "EAIDRS_RUNS_DIR"
ARTIFACTS_DIR_ENV = "EAIDRS_ARTIFACTS_DIR"


def repo_root() -> Path:
    """Return the repository root.

    Uses `EAIDRS_ROOT` if set, else the nearest parent of this file that contains both
    `pyproject.toml` and `configs/`, else the current working directory.
    """
    override = os.environ.get(ROOT_ENV)
    if override:
        return Path(override).resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file() and (parent / "configs").is_dir():
            return parent
    return Path.cwd().resolve()


def resolve_from_root(path: str | Path) -> Path:
    """Return `path` unchanged if absolute, otherwise relative to the repository root."""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else repo_root() / candidate


def _dir_from_env(env_name: str, default_name: str) -> Path:
    override = os.environ.get(env_name)
    return resolve_from_root(override) if override else repo_root() / default_name


def data_dir() -> Path:
    """Directory holding `raw/`, `processed/` and `MANIFEST.sha256`."""
    return _dir_from_env(DATA_DIR_ENV, "data")


def runs_dir() -> Path:
    """Directory where every tracked run writes its folder."""
    return _dir_from_env(RUNS_DIR_ENV, "runs")


def artifacts_dir() -> Path:
    """Directory for model bundles and other reusable artifacts."""
    return _dir_from_env(ARTIFACTS_DIR_ENV, "artifacts")


def manifest_path() -> Path:
    """Location of the committed SHA-256 manifest of the raw dataset files."""
    return data_dir() / "MANIFEST.sha256"
