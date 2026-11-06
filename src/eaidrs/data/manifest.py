"""SHA-256 manifest of raw dataset files (`data/MANIFEST.sha256`).

The manifest uses the `sha256sum` text format (`<hash>  <relative/posix/path>`), so it can
also be checked with standard tools. Every tracked run records the manifest's own hash, which
ties a result to the exact dataset bytes it was computed from.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

_CHUNK_BYTES = 1 << 20


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 of a file, reading it in 1 MiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(base_dir: Path, files: Iterable[Path]) -> dict[str, str]:
    """Hash `files` and key them by their POSIX path relative to `base_dir`."""
    entries: dict[str, str] = {}
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(f"cannot hash missing file: {path}")
        relative = path.resolve().relative_to(base_dir.resolve()).as_posix()
        entries[relative] = sha256_file(path)
    return dict(sorted(entries.items()))


def write_manifest(entries: dict[str, str], manifest_file: Path) -> None:
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{digest}  {relative}" for relative, digest in sorted(entries.items())]
    manifest_file.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def read_manifest(manifest_file: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line_no, raw in enumerate(manifest_file.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        digest, sep, relative = line.partition("  ")
        if not sep or len(digest) != 64:
            raise ValueError(f"{manifest_file}:{line_no}: malformed manifest line")
        entries[relative.strip()] = digest.lower()
    return entries


def verify_manifest(manifest_file: Path, base_dir: Path) -> list[str]:
    """Return a list of problems (missing files, hash mismatches). Empty means verified."""
    problems: list[str] = []
    for relative, expected in read_manifest(manifest_file).items():
        path = base_dir / relative
        if not path.is_file():
            problems.append(f"missing: {relative}")
        elif sha256_file(path) != expected:
            problems.append(f"hash mismatch: {relative}")
    return problems


def manifest_digest(manifest_file: Path) -> str | None:
    """SHA-256 of the manifest file itself (identifies the dataset version), or None."""
    return sha256_file(manifest_file) if manifest_file.is_file() else None
