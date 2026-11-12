# Data Card: CIC-IDS2017 (EA-IDRS)

Status: **skeleton**. Every `PENDING` value is filled from an `eaidrs audit` run folder
(DATA-04/05). Do not type numbers from memory or from other papers into this card.

## 1. Dataset identity

| Field | Value |
|---|---|
| Name | CIC-IDS2017 (Canadian Institute for Cybersecurity, University of New Brunswick) |
| Version used | Original release, "GeneratedLabelledFlows / TrafficLabelling" CSVs (**Proposed**, ADR-0007) |
| Source URL | PENDING (DATA-03) |
| Download date / by | PENDING |
| Licence / citation requirement | PENDING (DATA-03) |
| Files | 8 CSV files, Monday–Friday working hours (names in `configs/data/cicids2017.yaml`) |
| Integrity | SHA-256 per file in `data/MANIFEST.sha256`; manifest hash recorded in every run |
| Storage | `data/raw/cicids2017/` (gitignored) |
| Alternative | Corrected version by Engelen et al. (2021): not used yet; limitation / sensitivity check |

## 2. Intended use in this project

Flow-level, offline, chronological replay for a supervised NIDS baseline and (later) for the
drift-monitoring study. Public data only; no live or private traffic.

## 3. File inventory (from audit run `PENDING`)

| File | Day | Size | Rows | Columns | First timestamp | Last timestamp |
|---|---|---|---|---|---|---|
| PENDING | | | | | | |

## 4. Data-quality findings (from audit run `PENDING`)

| Issue | Count / detail | Handling |
|---|---|---|
| Leading/trailing spaces in column names | PENDING | Stripped (`cleaning.normalise_column_names`) |
| Duplicate column `Fwd Header Length.1` | PENDING (identical to `Fwd Header Length`?) | Dropped only if identical; otherwise kept and reported |
| Blank rows (no label) | PENDING | Dropped, counted per file |
| Infinite values (e.g. `Flow Bytes/s`, `Flow Packets/s`) | PENDING | Replaced by NaN (tree models handle missing values natively; no imputation fitted) |
| NaN values | PENDING | Kept as NaN, counted |
| Non-numeric values in numeric columns | PENDING | Coerced to NaN, counted |
| Negative values in counters/durations | PENDING | Kept, reported (decision PENDING) |
| Constant columns | PENDING | Removed by the feature pipeline using **training data only** (FEAT-01) |
| Exact duplicate rows | PENDING | Reported; decision PENDING (DATA-08) |
| Label encoding errors (web-attack dash) | PENDING | Normalised to `Web Attack - <type>` |
| Unparseable timestamps | PENDING | Rows dropped and counted; must be ~0 |
| 12-hour timestamps without AM/PM | PENDING (to verify) | Hours below 8 shifted +12 h (capture ran ~08:00–17:00) |

## 5. Class distribution by day (from audit run `PENDING`)

| Label | Monday | Tuesday | Wednesday | Thursday | Friday | Total |
|---|---|---|---|---|---|---|
| PENDING | | | | | | |

Per-class first/last timestamp (attack episodes): PENDING.

## 6. Chronological split (ADR-0008, **Proposed**)

| Item | Value |
|---|---|
| Strategy | PENDING (`global_time` vs `grouped_time`) |
| Boundaries / fractions | PENDING |
| Reason | PENDING |
| Rows per split | PENDING |
| Minimum support for an "evaluable" class | PENDING (config `min_class_support`) |

Class × split table: PENDING.
Evaluable classes for RQ1: PENDING.
Label grouping applied (ADR-0006): PENDING.

## 7. Features

| Group | Columns | Used as model features? |
|---|---|---|
| Identifiers | Flow ID, Source IP, Source Port, Destination IP, Destination Port, Protocol, Timestamp | **No** (shortcut/leakage risk; kept as metadata for display) — decision to confirm in FEAT-01 |
| Flow statistics | 77 columns listed in `configs/data/cicids2017.yaml` | Yes, minus constant columns found on train |
| Label | `Label` → `label` | Target only |

## 8. Known limitations

- Testbed traffic from 2017; may not represent current enterprise networks.
- Published analyses report labelling and feature-extraction problems (Engelen et al., 2021, to verify).
- Most attack types occur on a single day, in short episodes. This limits natural temporal drift
  and the number of classes evaluable under a strict global chronological split.
- Several classes are very rare. Rare-class metrics need their support reported next to them.
