# Demo Runbook (draft)

Status: **draft**. Steps marked *(after APP-01)* do not work yet. Owner: Aamish (DOC-06),
verified by someone who did not build the app (QA-04).

Target: a 5–7 minute live demo that works **offline**, from a laptop that already has the
environment, the dataset manifest verified, and the model bundle built.

## Before the presentation (day before)

1. `git checkout v0.1-minor-eval` and `uv sync --locked --all-groups`.
2. `uv run pytest` must pass.
3. `uv run eaidrs manifest verify` must pass (dataset intact).
4. *(after MODEL-04)* Check that the model bundle exists under `artifacts/bundles/`.
5. *(after APP-01)* Start the app once to warm caches, then close it.
6. Copy the backup video, screenshots and run folders to a USB drive.
7. Disable notifications, set the display to 100% zoom, close other apps.

## Live script (timings are targets)

| Time | What we show | Command / action | Say |
|---|---|---|---|
| 0:00–0:45 | Repository + CI | Browser: repo, merged PRs, green CI | "Every result maps to a commit and a config." |
| 0:45–1:45 | Data audit | Open the audit `audit_report.md` from the run folder | Class × day table; why the split strategy matters |
| 1:45–2:45 | Baseline results | Open `metrics.json` / classification report / confusion matrix of the chosen run | Validation only; test split is sealed |
| 2:45–5:30 | Prototype *(after APP-01)* | `uv run --group dashboard streamlit run apps/dashboard/app.py` | Pick a flow → prediction → probabilities → SHAP top features → plain-language explanation |
| 5:30–6:30 | What comes next | Architecture slide (M1–M4, delayed labels) | M3 vs M4 at a matched false-alarm budget |

## Fallbacks

| Failure | Fallback |
|---|---|
| App does not start | Play the backup recording |
| Laptop fails | Second laptop with the same tag + bundle (Akshat's machine) |
| No internet | Nothing in the demo needs internet; show the repo from local clone + screenshots |
| Question about a number | Open the run folder that produced it (evidence register) |
