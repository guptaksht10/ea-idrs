# ADR-0001: Single Python monorepo with an installable `eaidrs` library

- **Status:** Accepted (blueprint §3, §4)
- **Date:** 2026-11-06

## Context
Training, SHAP explanation, the Streamlit demo and (later) the API must use the same
preprocessing and feature order. If they live in separate repositories they drift apart.
Every reported number must also map to one commit.

## Decision
- One repository. All Python code lives in the `eaidrs` package (`src/` layout), installed into
  the project environment by `uv sync`. Apps and experiments are thin drivers that import it.
- Python **3.12** (already pinned in the repository's first commit; the blueprint said 3.11).
  The package declares `>=3.11,<3.14`, so either interpreter works. Lockfile: `uv.lock` at the root.
- Tooling: ruff (lint + format), mypy, pytest + coverage, import-linter, GitHub Actions.

## Consequences
- One `uv.lock`, one CI workflow, and atomic PRs when the feature schema changes.
- Needs folder discipline; import-linter contracts enforce the layering.
- The root `pyproject.toml` is new. `ml-service/pyproject.toml` stays untouched until the
  legacy-scaffold decision (ADR-0002).
