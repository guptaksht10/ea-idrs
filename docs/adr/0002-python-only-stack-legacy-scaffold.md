# ADR-0002: Python-only stack; Express/React scaffold is legacy

- **Status:** Accepted for the architecture. **Removing the legacy folders is Proposed** (needs Akshat's agreement).
- **Date:** 2026-11-06

## Context
The first commit created `frontend/` (Vite React template), `backend/` (Express, empty
`src/index.js`) and `ml-service/` (FastAPI "hello" package whose Dockerfile references a
missing `requirements.txt`). The approved research plan specifies FastAPI + SQLite + Streamlit.
The blueprint drops the Express gateway and the React dashboard.

## Decision
- No Express gateway and no React dashboard in BTP scope. FastAPI arrives in Phase 3 as
  `apps/api/`, importing `eaidrs`.
- The three folders are marked legacy. Nobody extends them. CI and the linters ignore them.
- Proposed follow-up PR (`chore/<n>-remove-legacy-scaffold`, owner Akshat): delete
  `frontend/`, `backend/`, `ml-service/` and the root `compose.yaml` that builds them. They
  contain no project logic. The FastAPI service is re-created later under `apps/api/`.

## Consequences
- Less code to maintain and one language for the team.
- Until the follow-up PR merges, the root `compose.yaml` does not build (the ml-service
  Dockerfile is broken). The README says so.
