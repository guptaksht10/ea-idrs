# ADR-0005: YAML configs validated by pydantic (decision D7)

- **Status:** Accepted for the minor evaluation; revisit before the Experiment G sweeps
- **Date:** 2026-11-06

## Context
All tunable values (paths, split boundaries, model hyperparameters, seeds) must come from
config files so every run can be reproduced. The options are YAML + pydantic, or Hydra.

## Decision
Plain YAML files in `configs/`, loaded into pydantic models with `extra="forbid"` so typos
fail fast. Each run copies the exact config files into its run folder.

## Consequences
No extra framework to learn during the 10-day sprint. If the Experiment G parameter sweeps
(Jan 2027) become painful, Hydra can be adopted then.
