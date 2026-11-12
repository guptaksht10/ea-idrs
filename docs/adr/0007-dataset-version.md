# ADR-0007: CIC-IDS2017 version and storage (decision D2)

- **Status:** **Proposed: requires guide confirmation**
- **Date:** 2026-11-06

## Context
Engelen, Rimmer & Joosen (2021) reported labelling and feature-extraction problems in
CIC-IDS2017 and released a corrected version (verify the reference before citing it).
The chronological split needs per-flow timestamps. These are in the original
"GeneratedLabelledFlows / TrafficLabelling" CSVs but **not** in the "MachineLearningCVE" CSVs.

## Decision (proposed)
- Primary dataset for the minor evaluation: **original CIC-IDS2017, TrafficLabelling CSVs**
  (8 files, Monday–Friday). The literature we compare with uses it, and it has timestamps.
- The corrected version is recorded as a known limitation and a possible sensitivity check
  after Nov 17. The loader is config-driven, so a second dataset config can be added later.
- Data never enters git. `data/MANIFEST.sha256` records the SHA-256 of every raw file. Each run
  records the manifest's own hash. A hash mismatch is a hard failure.

## Consequences
Known dataset issues (Infinity values, duplicated column, label encoding, timestamp format)
are handled in `eaidrs.data.cleaning` and reported in the data card. If the guide prefers the
corrected version, only the dataset config and column map change.
