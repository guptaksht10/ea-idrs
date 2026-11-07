# Experiment Log

A dated, human-written diary of what was tried, what failed and why decisions were made.
Failed and discarded runs are recorded too. Newest entries at the top.
Format: date · author · run ID (if any) · what · result · decision.

---

## 2026-11-06 · Ankit Raj · DATA-00 verification (synthetic fixtures)

**What:** verified the data pipeline on branch `feat/2-cicids-data-pipeline`.

**Result (synthetic pipeline tests, not research evidence):**
- `uv run pytest`: 55 passed; coverage 93% of `eaidrs` (statement + branch).
- ruff, ruff format, mypy (15 files) and import-linter (1 contract kept) all pass.
- Scale check on a 400k-row synthetic file with the real schema: read 2.1 s, clean 2.9 s,
  peak traced memory 0.88 GB, cleaned frame 199 MB. Extrapolated to ~2.8M rows: well within
  a 15 GB laptop. To be re-measured on the real files in DATA-02.
- On the fixtures, the global day split leaves the Thursday-only class out of training, as
  ADR-0008 anticipates. Whether this holds for the real data is measured in DATA-04.

---

## 2026-11-06 · Ankit Raj · no run

**What:** repository audit and engineering bootstrap (ENG-01); data-pipeline foundation on
synthetic fixtures (DATA-00).

**Result:**

- Repository contained template scaffolding only (React template, empty Express entry file,
  FastAPI hello package). No research code, tests, CI or data. See
  `docs/minor-evaluation/repository-audit.md`.
- Python was not installed on Ankit's machine: installed uv 0.13.7 and CPython 3.12.16.
- Locked environment resolves on Python 3.12 (key versions recorded in `uv.lock`).
- Data pipeline (manifest, loading, cleaning, chronological splits, audit, run tracking) is
  implemented and tested **on synthetic fixtures only**. No result from real data exists yet.

**Decisions / open items:**

- Split strategy is not chosen. A day-based split is expected to remove most attack classes
  from training; both strategies are implemented and will be compared in the audit (ADR-0008).
- D1 (multi-class) and D2 (dataset version) proposed, awaiting the guide (ADR-0006, ADR-0007).
- Dataset assumptions to verify on real files on 8 Nov: file names, timestamp format,
  afternoon-hour fix, label spellings (`VERIFY` markers in `configs/data/cicids2017.yaml`).
