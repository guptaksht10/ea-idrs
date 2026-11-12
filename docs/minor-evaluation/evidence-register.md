# Evidence Register (minor evaluation)

Rule: a row is filled only from something that actually ran. Screenshots come from the real
running system, never mock-ups. Figures are copied from run folders, never re-drawn by hand.
Store binary evidence (screenshots, video) in the team's shared drive folder
`EA-IDRS/minor-eval-evidence/` (not in git) and reference it here by file name.

| # | Evidence | Expected proof | Task | Location / reference | Status |
|---|---|---|---|---|---|
| E1 | Repository and architecture | Repo link, `docs/architecture.md`, ADRs, merged PRs | ENG-01, ENG-03 | PENDING (PRs not opened) | [~] |
| E2 | Development setup | `uv sync` + `uv run pytest` output on all three machines | ENG-05 | PENDING | [ ] |
| E3 | Dataset source and integrity | `data/README.md`, committed `data/MANIFEST.sha256`, verify output on two machines | DATA-01, DATA-03 | PENDING | [ ] |
| E4 | Data audit | Audit run folder: inventory, quality report, class × day, class × split | DATA-04 | PENDING | [ ] |
| E5 | Data card | `docs/data-card.md` citing the audit run ID | DATA-05 | PENDING | [ ] |
| E6 | Chronological split | `split_summary.json` (boundaries, per-class counts), invariant check output, ADR-0008 | DATA-06, DATA-07 | PENDING | [ ] |
| E7 | ML baseline | Two run folders (XGBoost, LightGBM): config, git commit, data hash, `metrics.json`, `classification_report.csv`, confusion matrix | MODEL-01, MODEL-03 | PENDING | [ ] |
| E8 | Result verification | Recomputed metrics note in the experiment log | MODEL-05 | PENDING | [ ] |
| E9 | Model bundle + card | `bundle.json`, round-trip test, `docs/model-card.md` | MODEL-04, DOC-04 | PENDING | [ ] |
| E10 | SHAP explanations | Run folder with SHAP values + plots for 2–3 real validation flows | XAI-01, XAI-02 | PENDING | [ ] |
| E11 | Streamlit application | Screenshots of the running app + the start command | APP-01 | PENDING | [ ] |
| E12 | Quality | CI run link (lint, types, tests, coverage) on `master` | QA-01, REL-01 | PENDING | [ ] |
| E13 | Reproducibility | Fresh-clone rerun on a second machine with matching metrics | QA-03 | PENDING | [ ] |
| E14 | Git workflow | Issue list, PR list with reviews, branch rule screenshot | ENG-02..04 | PENDING | [ ] |
| E15 | Presentation | Slides, demo runbook, rehearsal notes, backup video | REL-02, REL-03 | PENDING | [ ] |

## Screenshot log

| File | What it shows | Taken by | Date | Commit | Run ID |
|---|---|---|---|---|---|
| | | | | | |
