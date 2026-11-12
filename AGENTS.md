# EA-IDRS — AI Agent Instructions

## Project overview
EA-IDRS is an Explanation-Aware Intrusion Detection and Response System.
It studies whether explanation-based drift monitoring provides additional
warning of attack-class-specific recall degradation when labels are delayed.

Source of truth, in priority order:
1. The approved research plan (`EA-IDRS_Research_Plan_Summary.pdf`, kept outside git).
2. The engineering blueprint, as summarised in `docs/architecture.md` and `docs/adr/`.
3. Older documents (synopsis, `PROJECT_REFERENCE.md`, `detailed_research_plan.md`) are
   background only. See `docs/document-reconciliation.md` for the conflicts already resolved.

## Repository structure (approved Python monorepo, ADR-0001)
- `src/eaidrs/`: the shared library (data, features, model, explain, later monitor/replay/evaluation)
- `configs/`: YAML configs. Tunable numbers live here, not in code.
- `tests/`: pytest suite. Uses synthetic fixtures with the real CIC-IDS2017 schema.
- `apps/dashboard/`: Streamlit app (minor-evaluation prototype). `apps/api/` (FastAPI) comes in Phase 3.
- `docs/`: architecture, ADRs, data/model cards, experiment log, minor-evaluation plan.
- `data/`, `artifacts/`, `runs/`: gitignored outputs (datasets, model bundles, run folders).
- `frontend/`, `backend/`, `ml-service/`: **legacy scaffold** from the first commit. Do not extend
  them. Their removal is a pending team decision (ADR-0002).

## Architecture rules
- Python only: FastAPI for the API (Phase 3), Streamlit for the dashboard. No Express gateway,
  no React frontend, no PostgreSQL/Redis for the BTP scope (ADR-0002, ADR-0003, ADR-0009).
- Apps and experiments stay thin and import `eaidrs`. Preprocessing exists once.
- Keep research evaluation separate from the live inference path.
- **Label firewall:** monitoring and alert-generation code never receives true labels.
  Only the evaluator reads released labels (ADR-0004).
- **Chronological splits only.** Never use a random split. Fit preprocessing on train only.
  The test split is sealed until the test protocol is approved.
- Inside Docker Compose, services talk via service names, not `localhost`. Containers bind `0.0.0.0`.

## General coding rules
- Make focused changes; avoid unrelated refactors.
- Inspect the relevant files before editing and follow existing conventions.
- Do not invent APIs, model outputs, dataset fields, metrics or environment variables.
- Never fabricate results. Unknown values are written `PENDING`. Fixture results are labelled synthetic.
- Keep secrets out of source control; document variables in `.env.example`.
- Update documentation and tests when behaviour or configuration changes.
- Do not add dependencies unless needed; explain why when adding one (`uv add`).
- Never commit datasets, model binaries, run folders, caches, local databases or notebook outputs.

## Python conventions
- Python 3.12 via `uv` (`uv sync --all-groups`, `uv run ...`). Lockfile: `uv.lock`.
- Type hints and docstrings on public functions. `ruff` + `mypy` + `pytest` must pass.
- Commands: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`,
  `uv run lint-imports`, `uv run pytest --cov`.

## Generated and dependency directories
Do not inspect, search, edit, or summarize files inside:
- `node_modules/`
- `.venv/`, `venv/`, `env/`
- `__pycache__/`
- `dist/`, `build/`, `.next/`, `coverage/`
- `data/`, `runs/`, `artifacts/` (large generated outputs; read specific summary files only)

Use manifests and lockfiles to understand dependencies instead.

## Before finishing a task
- Summarize what changed and list relevant files.
- Mention commands or tests run and whether they passed.
- Clearly state anything not tested or any assumptions made.

## Engineering role and standards

Act as a professional software engineer building a research-grade product.
Apply industry standards for architecture, security, reliability, testing,
documentation, accessibility, and code quality, proportionate to the project's
research scope.

- Prefer clear, modular, maintainable solutions over shortcuts or unnecessary complexity.
- Keep research claims, experimental results, and implementation behavior accurate and reproducible.
- Consider performance, observability, failure handling, and deployment implications.
- Explain significant trade-offs and flag risks or uncertainties.
- Avoid introducing production-scale infrastructure unless the project needs it.
