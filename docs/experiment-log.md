# Experiment Log

A dated, human-written diary of what was tried, what failed and why decisions were made.
Failed and discarded runs are recorded too. Newest entries at the top.
Format: date · author · run ID (if any) · what · result · decision.

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
