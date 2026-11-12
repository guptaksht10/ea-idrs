# Minor-Evaluation Checklist (17 Nov 2026)

Legend: `[ ]` not started · `[~]` in progress · `[x]` completed **and verified** · `[!]` blocked.
A task becomes `[x]` only when its evidence exists and someone other than the owner has checked it.
Owners: **AG** Akshat Gupta · **AR** Ankit Raj · **AH** Aamish Hussain.
Branch numbers other than #1/#2 are filled in once the issues exist (`<n>`).

Status last updated: 2026-11-06 (AR).

---

## Prep — Fri 6 Nov

- [~] **ENG-01 · Repository audit and engineering bootstrap**
  AR · P0 · 4 h · Depends: — · Branch `chore/1-repo-bootstrap` · PR: **not opened** (AR has read-only access, see ENG-02)
  - Files: `pyproject.toml`, `uv.lock`, `.python-version`, `.gitignore`, `.github/`, `CONTRIBUTING.md`, `README.md`, `AGENTS.md`, `docs/`
  - Accept: `uv sync --locked` works on a clean machine; ruff, ruff format, mypy and pytest pass; audit report and plan committed; no data or secrets committed.
  - Evidence: local check output in PR description; CI run on the PR; `docs/minor-evaluation/repository-audit.md`.

- [~] **DATA-00 · Data-pipeline foundation on synthetic fixtures**
  AR, reviewer AG · P0 · 4 h · Depends: ENG-01 · Branch `feat/2-cicids-data-pipeline` (stacked on #1) · PR: **not opened**
  - Files: `src/eaidrs/{core,data,tracking}/`, `src/eaidrs/cli.py`, `configs/data/cicids2017.yaml`, `configs/split/*.yaml`, `tests/`
  - Accept: tests cover NaN/Inf cleaning, label normalisation, timestamp parsing, chronological split with no overlap (train < val < test), manifest tamper detection, audit counts, run-folder contents; import-linter layering contract passes.
  - Evidence: pytest + coverage output; CI on the PR.

## Sat 7 Nov — Repository and access

- [ ] **ENG-02 · Repository access and branch protection**
  AG · P0 · 1 h · Depends: — · Branch: none (GitHub settings) · PR: n/a
  - Accept: AR and AH have Write access; squash-only merges; auto-delete head branches; `master` requires PR + 1 approval + CI check; force-push blocked; visibility decision recorded (R9).
  - Evidence: screenshot of the branch rule; AR can push a branch.

- [ ] **ENG-03 · Push bootstrap branches, open and merge PR 1 and PR 2**
  AR (push) + AG (review) · P0 · 1 h + 3 h review · Depends: ENG-02, ENG-04 · Branches: `chore/1-repo-bootstrap`, `feat/2-cicids-data-pipeline`
  - Accept: CI green on both PRs; reviewed by AG; squash-merged in order (PR 1 then PR 2).
  - Evidence: merged PR links; green CI run links.

- [ ] **ENG-04 · Milestone, labels and issues**
  AR · P0 · 1.5 h · Depends: ENG-02 · Branch: none
  - Accept: milestone "Minor evaluation (17 Nov)"; one issue per task in this file, created in order so ENG-01 = #1, DATA-00 = #2; labels P0/P1/P2 + area.
  - Evidence: link to the milestone page.

- [ ] **ENG-05 · Every member reproduces the environment**
  AG, AR, AH · P0 · 0.5 h each · Depends: ENG-03
  - Accept: `uv sync --all-groups` and `uv run pytest` pass on all three machines.
  - Evidence: terminal output saved to the evidence folder (one per member).

- [ ] **RES-01 · Guide meeting request: open decisions**
  AR · P0 · 1 h · Depends: —
  - Accept: agenda sent covering D1 multi-class (ADR-0006), D2 dataset version (ADR-0007), split strategy (ADR-0008), 3-member active team, evaluation dates (Mar/Apr vs Apr/May 2027).
  - Evidence: sent message / meeting notes in `docs/meeting-notes/`. **Do not record an approval that was not given.**

- [ ] **DOC-01 · Documentation inventory**
  AH · P1 · 2 h · Depends: —
  - Files: `docs/minor-evaluation/evidence-register.md`
  - Accept: list of every doc (repo + local planning docs) with owner, status and whether it is superseded.
  - Evidence: inventory table merged.

## Sun 8 Nov — Data acquisition

- [ ] **DATA-01 · Download CIC-IDS2017 and commit the checksum manifest**
  AG (download) + AR (verify on second machine) · P0 · 2 h + 1 h · Depends: ENG-03 · Branch `chore/<n>-cicids-manifest`
  - Files: `data/raw/cicids2017/` (gitignored), `data/MANIFEST.sha256`, `data/README.md`
  - Accept: 8 TrafficLabelling CSVs present; `uv run eaidrs manifest create` output committed; `uv run eaidrs manifest verify` passes on **two** machines; download source + date recorded.
  - Evidence: committed manifest; verify output from both machines.

- [ ] **DATA-02 · Load and clean the real files; fix config mismatches**
  AG · P0 · 3 h · Depends: DATA-01 · Branch `fix/<n>-real-data-schema`
  - Files: `configs/data/cicids2017.yaml`, `src/eaidrs/data/`
  - Accept: all assumptions marked `VERIFY` in the dataset config confirmed or corrected (file names, columns, timestamp format, afternoon-hour fix, label spellings); zero unparsed timestamps or each one explained; tests updated for any new quirk.
  - Evidence: run folder from `uv run eaidrs audit ...`; PR with the config diff.

- [ ] **DATA-03 · Dataset source documentation**
  AH · P0 · 2 h · Depends: DATA-01
  - Files: `data/README.md`
  - Accept: source URL, version, licence/citation, file list with sizes, download date and who downloaded it.
  - Evidence: merged PR.

## Mon 9 Nov — Dataset audit

- [ ] **DATA-04 · Dataset audit run (both split strategies)**
  AR · P0 · 4 h · Depends: DATA-02 · Branch `docs/<n>-dataset-audit`
  - Accept: one audit run folder containing file inventory, quality report (NaN, Inf, negative, constant columns, duplicates), class × day table, per-class time ranges, class × split tables for both strategies; findings logged in `docs/experiment-log.md`.
  - Evidence: run folder path + `audit_report.md` from it.

- [ ] **DOC-02 · Literature matrix and reference verification**
  AH (AR reviews content) · P0 · 3 h · Depends: —
  - Files: `docs/literature-matrix.md`
  - Accept: the five PDF references with verified DOI links; a "full text read?" column; Engelen et al. reference verified or marked unverified.
  - Evidence: merged PR.

## Tue 10 Nov — Temporal pipeline

- [ ] **DATA-05 · Data card with real audit numbers**
  AR (content) + AH (formatting) · P0 · 3 h + 1 h · Depends: DATA-04
  - Files: `docs/data-card.md`
  - Accept: every `PENDING` in sections 3–6 replaced by numbers copied from the audit run; run ID cited.
  - Evidence: merged PR; run ID in the card.

- [ ] **DATA-06 · Split decision proposal**
  AR · P0 · 3 h · Depends: DATA-04
  - Files: `docs/adr/0008-chronological-split-strategy.md`, `configs/split/*.yaml`
  - Accept: chosen strategy + boundaries + evaluable-class list + any label grouping (ADR-0006), justified with audit numbers; sent to the guide; status stays "Proposed" until the guide confirms.
  - Evidence: updated ADR; message to the guide.

- [ ] **DATA-07 · Prepare processed splits and verify no leakage**
  AR · P0 · 2 h · Depends: DATA-06 · Branch `test/<n>-split-leakage-checks`
  - Accept: `uv run eaidrs prepare` writes train/val and sealed test; split invariants pass on real data; leakage checklist done (identifier columns excluded from features, no test rows in train/val, preprocessing fitted on train only once FEAT-01 lands).
  - Evidence: prepare run folder (`split_summary.json`); checklist in PR.

- [ ] **FEAT-01 · Feature contract and preprocessor**
  AG · P0 · 5 h · Depends: DATA-02 · Branch `feat/<n>-feature-pipeline`
  - Files: `src/eaidrs/features/`, `tests/unit/features/`
  - Accept: ordered feature list + hash; identifier and metadata columns never used as features; constant-column removal fitted on train only; float32 output; save/load round-trip; tests for each.
  - Evidence: PR with test output.

- [ ] **TEST-01 · Fixture support for feature and model tests**
  AH (AR pairs) · P1 · 2 h · Depends: DATA-00
  - Files: `tests/conftest.py`
  - Accept: helper that returns a small cleaned frame with 3+ classes for model tests.
  - Evidence: merged PR.

## Wed 11 Nov — Baseline training

- [ ] **MODEL-02 · Pre-declare model-selection criterion**
  AR · P0 · 2 h · Depends: DATA-06 · Branch `docs/<n>-selection-criterion`
  - Accept: before any results are seen, record in `docs/experiment-log.md` the selection metric (proposed: macro-F1 on validation over evaluable classes), tie-breakers and the fixed hyperparameters.
  - Evidence: dated log entry committed before the MODEL-01 run timestamps.

- [ ] **MODEL-01 · XGBoost and LightGBM multi-class baselines (Experiment A, validation only)**
  AG · P0 · 8 h · Depends: FEAT-01, DATA-07, MODEL-02 · Branch `exp/<n>-baseline-xgb-lgbm`
  - Files: `src/eaidrs/model/train.py`, `configs/model/{xgboost,lightgbm}.yaml`
  - Accept: both models trained from config with a fixed seed and class weights; each run folder has config, environment, git commit, data manifest hash, timings; nothing reads the test split.
  - Evidence: two run folders.

## Thu 12 Nov — Evaluation and bundle

- [ ] **MODEL-03 · Validation metrics module**
  AR · P0 · 4 h · Depends: MODEL-01 (interface) · Branch `feat/<n>-classification-metrics`
  - Files: `src/eaidrs/evaluation/classification.py`, tests
  - Accept: per-class precision/recall/F1 + support, macro and weighted averages, derived binary attack-vs-benign metrics, confusion matrix PNG, `classification_report.csv`, `metrics.json`; matches scikit-learn on a fixture.
  - Evidence: tests; metrics files in both MODEL-01 run folders.

- [ ] **MODEL-04 · Model bundle**
  AG · P0 · 4 h · Depends: MODEL-01, FEAT-01 · Branch `feat/<n>-model-bundle`
  - Files: `src/eaidrs/model/bundle.py`, `artifacts/bundles/<id>/` (gitignored)
  - Accept: bundle = model + preprocessor + `bundle.json` (classes, feature-contract hash, git commit, data manifest hash, library versions, validation metrics); load → predict gives identical output; probability rows sum to 1; classes valid.
  - Evidence: round-trip test; bundle folder listing.

- [ ] **MODEL-05 · Independent verification of baseline results**
  AR · P0 · 2 h · Depends: MODEL-03
  - Accept: metrics recomputed from saved predictions match `metrics.json`; supports match the data card; model choice follows the MODEL-02 criterion; any surprise (e.g. near-perfect score) investigated and logged.
  - Evidence: verification note in `docs/experiment-log.md`.

- [ ] **DOC-04 · Model card**
  AH (AR reviews) · P0 · 3 h · Depends: MODEL-05
  - Files: `docs/model-card.md`
  - Accept: all fields filled from bundle + run folders; limitations section; validation-only statement.
  - Evidence: merged PR.

## Fri 13 Nov — Explainability

- [ ] **XAI-01 · SHAP TreeExplainer wrapper**
  AG · P0 · 5 h · Depends: MODEL-04 · Branch `feat/<n>-shap-explanations`
  - Files: `src/eaidrs/explain/`, tests
  - Accept: works for the selected model; returns per-class SHAP values + base values; local top-k for the predicted class; additivity check passes (base + Σ SHAP ≈ raw margin); runs on a fixture model in CI.
  - Evidence: tests; timing for one flow logged.

- [ ] **XAI-02 · Representative flow explanations**
  AR (selection + interpretation) with AG · P0 · 3 h · Depends: XAI-01
  - Accept: deterministic, pre-written selection rule (e.g. a correctly classified benign flow, a correctly classified attack flow, and one misclassified flow, from validation); SHAP CSV + plots saved in a run folder; interpretation text reviewed by both AG and AR, with no causal claims.
  - Evidence: run folder; interpretation text in the experiment log.

- [ ] **DOC-05 · Capture SHAP evidence**
  AH · P0 · 1 h · Depends: XAI-02
  - Accept: figures copied from the run folder (not re-drawn) into the evidence folder with run IDs.
  - Evidence: evidence-register rows filled.

## Sat 14 Nov — Prototype

- [ ] **APP-01 · Streamlit single-page prototype**
  AG · P0 · 7 h · Depends: MODEL-04, XAI-01 · Branch `feat/<n>-streamlit-demo`
  - Files: `apps/dashboard/app.py`, demo-sample builder in `eaidrs`
  - Accept: one command starts it; select a real validation flow (or enter values); prediction, class probabilities, top SHAP contributions, plain-language explanation, model metadata; works offline with no dataset re-download; no hand-typed predictions.
  - Evidence: screenshots from the running app; command in the runbook.

- [ ] **QA-01 · Integration tests**
  AR · P0 · 4 h · Depends: MODEL-04, XAI-01 · Branch `test/<n>-end-to-end`
  - Accept: fixture end-to-end test (prepare → train small model → bundle → explain) and Streamlit `AppTest` smoke test pass in CI.
  - Evidence: CI run.

- [ ] **DOC-06 · Demo runbook and user guide**
  AH · P0 · 2 h · Depends: APP-01 (draft can start earlier)
  - Files: `docs/minor-evaluation/demo-runbook.md`
  - Accept: step-by-step commands verified by someone who did not write the app.
  - Evidence: QA-04 log.

## Sun 15 Nov — QA and documentation

- [ ] **QA-02 · Bug fixing**
  AG · P0 · 4 h · Depends: QA-01, QA-04
  - Accept: every P0 bug from QA closed with a test where feasible.
  - Evidence: closed issues.

- [ ] **QA-03 · Fresh-clone reproducibility check**
  AR · P0 · 4 h · Depends: APP-01
  - Accept: on AR's machine: clone → `uv sync --locked` → manifest verify → prepare → train selected model with the same config/seed → metrics identical (or differences explained) → app runs.
  - Evidence: run folder + comparison note in the experiment log.

- [ ] **QA-04 · Manual demo test**
  AH · P0 · 2 h · Depends: APP-01, DOC-06
  - Accept: runbook followed exactly; every step passes or a bug issue is filed.
  - Evidence: dated test log.

- [ ] **DOC-07 · README final update**
  AH (AR reviews) · P0 · 2 h · Depends: QA-03
  - Accept: status section matches reality; commands copy-paste correctly.
  - Evidence: merged PR.

- [ ] **RES-02 · Research roadmap review**
  AR · P0 · 2 h · Depends: —
  - Files: `docs/research-roadmap.md`
  - Accept: M1–M4, label firewall, delayed-label replay, M3 vs M4 protocol, Experiments A–G and milestones; consistent with the PDF.
  - Evidence: merged PR.

- [ ] **DOC-08 · Architecture diagrams**
  AH · P1 · 2 h · Depends: —
  - Accept: current (Nov) and target (Phase 3–5) diagrams exported as images for slides, matching `docs/architecture.md`.
  - Evidence: image files + slide.

## Mon 16 Nov — Release

- [ ] **REL-01 · Feature freeze, final regression, release tag**
  AR (verify) + AG (tag) · P0 · 1 h + 0.5 h · Depends: QA-02, QA-03, QA-04
  - Accept: freeze at 12:00; CI green on `master`; checklist statuses true; tag `v0.1-minor-eval` on the verified commit.
  - Evidence: tag link; CI run link.

- [ ] **REL-02 · Presentation**
  AR (content) + AH (formatting) · P0 · 3 h + 3 h · Depends: MODEL-05, XAI-02
  - Files: `docs/minor-evaluation/presentation-outline.md`
  - Accept: every number on a slide has a run ID in the evidence register; pending items marked PENDING/Proposed.
  - Evidence: slide file; evidence register.

- [ ] **REL-03 · Rehearsals and backup recording**
  All · P0 · 2 h each · Depends: REL-01
  - Accept: two full rehearsals of the 5–7 minute demo; screen recording of the real app saved in two places; offline fallback (screenshots + run folders) ready.
  - Evidence: recording file location; rehearsal notes.

- [ ] **REL-04 · Final checklist and backups**
  AH · P0 · 1 h · Depends: REL-01
  - Accept: this checklist reviewed line by line; backups of slides, video and bundle on a USB drive and cloud drive.
  - Evidence: signed-off checklist.

---

## P1 / P2 (only after the day's P0 items are done)

- [ ] **ENG-06 · pre-commit hooks** (ruff, ruff-format, nbstripout) — AR · P1 · 1 h
- [ ] **ENG-07 · Remove legacy scaffold** (`frontend/`, `backend/`, `ml-service/`, root `compose.yaml`) after team agreement (ADR-0002) — AG · P1 · 1 h · Branch `chore/<n>-remove-legacy-scaffold`
- [ ] **DATA-08 · Duplicate-row analysis and decision** (within and across splits) — AR · P1 · 2 h
- [ ] **MODEL-06 · Validation-only operating threshold for P(attack)** — AG · P1 · 2 h
- [ ] **MODEL-07 · Second seed for both baselines** — AG · P1 · 1 h compute + 0.5 h
- [ ] **XAI-03 · SHAP runtime per flow** (first data point for RQ4) — AG · P1 · 1 h
- [ ] **MON-00 · Preliminary M1 (PSI) plot on validation windows**, clearly labelled *preliminary* — AR · P2 · 3 h
- [ ] **Corrected CIC-IDS2017 sensitivity check** — post-17 Nov · P2
