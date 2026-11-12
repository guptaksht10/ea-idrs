# ADR-0009: Streamlit single-page prototype for the minor evaluation (decision D8)

- **Status:** Accepted
- **Date:** 2026-11-06

## Context
The Nov 17 demo must show: network flow → preprocessing → frozen model → class probabilities
→ SHAP explanation, using the real trained bundle. The approved plan names a Streamlit analyst
dashboard. A React app would need an API layer first.

## Decision
One Streamlit page (`apps/dashboard/app.py`) that imports `eaidrs` directly and loads the model
bundle from `artifacts/`. It picks real flows from a small, locally generated demo sample of the
**validation** split, so the demo runs offline and never touches the sealed test split. No API
and no database for this milestone. One command starts it.

## Consequences
Fast to build and easy to test (`streamlit.testing.v1.AppTest`). The multi-page dashboard
(alerts, drift, response) and the API come in Phases 3–5.
