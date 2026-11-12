# Repository Audit — 2026-11-06

Audited by Ankit Raj at commit `51f21bb` on `master`, before any change.
Method: inspected every tracked file (except lockfiles and dependency folders), git history,
GitHub settings via `gh`, and the local toolchain. Nothing was assumed to work because a file
existed.

## 1. Git and GitHub

| Item | Finding |
|---|---|
| Remote | `github.com/guptaksht10/ea-idrs`, **public**, default branch `master` |
| History | 3 commits, all by Akshat on 2026-11-02 (initial commit, licence, "init: initialized the project structure") |
| Branches | `master` only |
| Issues / PRs | none |
| Branch protection | **none** on `master` |
| Merge settings | squash, merge commit and rebase all allowed; head branches not auto-deleted |
| Ankit's access | **READ only** (`dev-rajankit`): cannot push branches or open PRs from the repo |
| CI | none (`.github/` did not exist) |
| Untracked | `local-dev/` (planning documents, incl. roll numbers) — now gitignored |

## 2. What exists, and whether it works

| Component | Files | Status | Recommendation |
|---|---|---|---|
| React frontend | `frontend/` (Vite + React 19 template, counter demo) | **Template only**, no project code | Defer/remove (ADR-0002); Streamlit replaces it |
| Express backend | `backend/` (`package.json`, `src/index.js` is **0 bytes**) | **Not implemented**. `npm start` points at a missing root `index.js` | Remove (ADR-0002); FastAPI later |
| FastAPI ML service | `ml-service/` (`pyproject.toml` with only `fastapi`; `__init__.py` prints "Hello") | **Placeholder**. `project.scripts` points at a module `ml_service` that does not exist; Dockerfile needs a missing `requirements.txt` and starts gunicorn on an invalid module path | Remove; re-create as `apps/api/` in Phase 3 |
| Docker Compose | root `compose.yaml` + one per service | **Does not build** (ml-service Dockerfile) | Replace in Phase 3 (`infra/compose.yaml`) |
| Python research code | — | **Not present**: no data loading, preprocessing, model, SHAP, monitoring, evaluation | Build (this sprint) |
| Tests | — | none (backend `jest` script has no tests) | Build |
| Docs | `README.md` (2 lines), `AGENTS.md` (described Express + React) | Outdated | Rewritten |
| Dataset | — | **Not downloaded**; no manifest | DATA-01 on 8 Nov |
| Model artifacts / notebooks | — | none | — |
| TODOs in code | — | none found | — |

## 3. Local environment (Ankit's machine)

| Item | Finding |
|---|---|
| OS / RAM / disk | Windows 11 Pro, 15.3 GB RAM, 336 GB free on C: |
| Python | **not installed** before this audit → installed `uv 0.13.7` (winget) and CPython 3.12.16 (uv-managed) |
| `make` | not available → commands documented as `uv run ...` instead of a Makefile |
| Node / Docker / gh | Node 24, Docker 29.9, gh 2.103 (authenticated as `dev-rajankit`) |

## 4. Document conflicts

See [`../document-reconciliation.md`](../document-reconciliation.md). The main conflicts: the
older documents and `AGENTS.md` pushed Express + React + PostgreSQL + Redis, a binary
classifier, experiments 1–11 and a Mon–Wed / Thu / Fri day split. The approved PDF replaces all
of these.

## 5. Highest-risk dependencies

1. **Repository access** (ENG-02): nothing merges until Akshat grants write access and
   protects `master`.
2. **Dataset acquisition and real schema** (DATA-01/02): the loader's assumptions (file names,
   timestamp format, label spelling) must be verified on the real files.
3. **Split strategy** (ADR-0008): a pure day split is expected to leave most attack classes out
   of training. This must be measured and decided with the guide.
4. **Akshat's capacity**: model, SHAP and Streamlit are all on one person's critical path.

## 6. What is realistic by 17 Nov

Realistic: data manifest + audit + data card, chronological split, XGBoost and LightGBM
validation baselines with per-class metrics, model bundle, SHAP explanations for 2–3 real flows,
a one-page Streamlit demo, CI with tests, and the research roadmap.

Not realistic and out of scope: M1–M4 implementation, delayed-label replay, evaluator and CIs,
API/DB, Docker simulation, response agent, UNSW-NB15.

## 7. Changes made after this audit (6 Nov)

- `chore/1-repo-bootstrap`: root `pyproject.toml` + `uv.lock`, CI workflow, PR/issue templates,
  CODEOWNERS, CONTRIBUTING, README, AGENTS.md, `.gitignore`, docs and this plan.
- `feat/2-cicids-data-pipeline`: data manifest, loading, cleaning, chronological splits, audit,
  run tracking, CLI and tests on synthetic fixtures. **Not yet run on real data.**
- Nothing in `frontend/`, `backend/` or `ml-service/` was modified or deleted.
