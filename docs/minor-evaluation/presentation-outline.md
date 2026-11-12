# Presentation Outline (17 Nov 2026, minor evaluation)

Rule: every number on a slide cites a run ID from the evidence register. Anything not yet
measured says **PENDING**; anything not yet confirmed by the guide says **Proposed**.

| # | Slide | Content | Source | Presenter |
|---|---|---|---|---|
| 1 | Title | EA-IDRS, research question, group GP050, guide | PDF | AR |
| 2 | Problem | Confident predictions while one attack class's recall falls; labels arrive late | PDF §2 | AR |
| 3 | Research question + RQ1–RQ4 | Primary: M4 vs M3 lead time at a matched false-alarm budget | PDF §3 | AR |
| 4 | Related work + gap | Literature matrix; we do **not** claim SHAP drift detection is new | `docs/literature-matrix.md` | AR |
| 5 | Study design | Frozen model, chronological windows, monitors without labels, separate evaluator | `docs/research-roadmap.md` | AR |
| 6 | Architecture | One library, two drivers; what is built vs later | `docs/architecture.md` | AG |
| 7 | Dataset + audit | Version, manifest, quality issues found, class × day table | data card, audit run | AR |
| 8 | Chronological split | Strategy, boundaries, per-class support, why | ADR-0008, `split_summary.json` | AR |
| 9 | Baseline results | XGBoost vs LightGBM per-class P/R/F1 on **validation**; selection rule declared beforehand | MODEL-01/03 runs | AG |
| 10 | SHAP explanations | 2–3 real flows: prediction + top contributions; SHAP ≠ causation | XAI-02 run | AG |
| 11 | Live demo | Streamlit prototype | APP-01 | AG |
| 12 | Engineering quality | CI, tests, PR workflow, reproducibility check on a second machine | CI links, QA-03 | AR |
| 13 | Roadmap to Apr 2027 | Phases 3–6, Experiments A–G | delivery plan §8 | AR |
| 14 | Open decisions + risks | D1, D2, split, sparse classes, negative results are valid | ADRs | AR |
| 15 | Team contributions | Who did what, with PR/issue links | GitHub | AH |

Backup slides: confusion matrices, full class × split table, data-quality details, failed or
discarded runs from the experiment log.
