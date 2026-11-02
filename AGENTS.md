# EA-IDRS — AI Agent Instructions

## Project overview
EA-IDRS is an Explanation-Aware Intrusion Detection and Response System.
It studies whether explanation-based drift monitoring provides additional
warning of attack-class-specific recall degradation when labels are delayed.

## Repository structure
- `frontend/`: React + Vite + TypeScript user interface
- `backend/`: Express API and application orchestration
- `ml-service/`: FastAPI service for ML inference, explanations, and monitoring
- `research/`: experiments, evaluation scripts, notebooks, and research results
- `compose.yaml`: local multi-service orchestration

## Architecture
- The frontend communicates with the Express backend.
- Express communicates with FastAPI for model inference and ML-related operations.
- Inside Docker Compose, services should communicate using Compose service names,
  not `localhost` (for example, `http://ml-service:8000`).
- Keep research evaluation separate from the live inference path.
- Do not expose evaluation labels to live monitoring or alert-generation logic.
- Use chronological replay for drift experiments; avoid random splits that leak
  future information into earlier monitoring periods.

## General coding rules
- Make focused changes; avoid unrelated refactors.
- Inspect the relevant files before editing and follow existing conventions.
- Do not invent APIs, model outputs, dataset fields, or environment variables.
- Keep secrets out of source control. Use environment variables and provide
  placeholder values in `.env.example` files.
- Update documentation and tests when behavior or configuration changes.
- Do not add dependencies unless they are needed; explain why when adding one.
- Never commit generated dependencies, build output, caches, local databases,
  or private datasets.

## Service-specific guidance

### Frontend
- Use React, TypeScript, and the existing Vite setup.
- Keep API calls in the existing API/service layer when one exists.
- Do not hardcode backend URLs; use environment configuration.
- Keep UI components focused and reusable.

### Express backend
- Use ES modules (`import`/`export`) because the package is configured with
  `"type": "module"`.
- Keep routes, controllers, and service logic separated where the existing
  structure supports it.
- Validate incoming data and handle errors consistently.
- Do not put ML model logic in Express; call the FastAPI service.

### FastAPI / ML service
- Use Python and the existing `uv` project configuration.
- Keep model inference, explanation generation, and drift monitoring modular.
- Make preprocessing consistent between training and inference.
- Keep training and offline evaluation separate from online inference.
- Record experiment settings and metrics so results can be reproduced.

## Docker
- Each service has its own Dockerfile.
- Keep the shared Compose configuration at the repository root.
- Ensure containerized servers bind to `0.0.0.0`.
- Do not assume `localhost` refers to another container.

## Generated and dependency directories
Do not inspect, search, edit, or summarize files inside:
- `node_modules/`
- `.venv/`, `venv/`, `env/`
- `__pycache__/`
- `dist/`, `build/`, `.next/`, `coverage/`

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