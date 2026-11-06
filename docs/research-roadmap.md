# Research Roadmap: M1–M4, delayed labels, and the M3 vs M4 protocol

Source: approved research plan (PDF §3–§4) and blueprint §6.5–§6.6. Nothing here is
implemented yet. It is the design the team builds from Phase 3 (from 18 Nov 2026).

## 1. The question

> **RQ1 (primary).** Under delayed-label conditions, when does adding class-conditional SHAP
> monitoring to feature-drift and prediction-score monitoring give earlier warning of
> attack-class-specific recall degradation, at a matched false-alarm rate?

RQ2: which controlled shifts trigger which monitors, and which actually reduce class recall.
RQ3: sensitivity to window size, attribution aggregation, alert threshold and class prevalence.
RQ4: computational overhead of SHAP monitoring.

A SHAP shift is a **diagnostic signal, not proof** that the model degraded. Only the evaluator,
using delayed ground truth, can say whether recall actually fell.

## 2. Study design

1. Train a gradient-boosted tree on the **training** split. Freeze it.
2. Replay a later split as ordered, fixed-size windows (window size chosen on validation).
3. For each window: predictions, class probabilities, and SHAP values on a fixed, seeded sample.
4. Four monitors score **the same window object**:

| Monitor | Signal | Purpose |
|---|---|---|
| M1 Feature | PSI and/or KS on selected input features | Input-distribution baseline |
| M2 Score | Attack-probability distribution + predicted class mix | Output-behaviour baseline |
| M3 Combined | M1 + M2 | Does output monitoring help without SHAP? |
| M4 Proposed | M3 + class-conditional SHAP attribution drift (grouped by **predicted** class) | Incremental value of explanation monitoring |

5. Labels never reach the monitors. A label ledger releases each window's labels to the
   evaluator only after `label_delay_windows` windows (Experiment E).
6. The evaluator computes per-class recall per window, detects degradation onsets, and
   compares them with monitor alerts.

## 3. Label firewall (ADR-0004)

- Monitors accept an `UnlabelledWindow` type with no label field.
- import-linter forbids `monitor`, `explain`, `model`, `replay` from importing `evaluation`; CI fails otherwise.
- Tests assert that windows contain no label columns and that the ledger never releases labels early.

## 4. M3 vs M4 comparison protocol (Experiment F)

Everything below is fixed **on validation** and frozen before any test window is scored.

1. Run every monitor over the validation stream with no injected shift.
2. Choose each monitor's threshold so that all monitors share the **same false-alarm budget**
   (e.g. ≤ 2% of no-degradation windows alert).
3. Fix the degradation criterion (recall drop δ below validation recall for k consecutive
   windows with at least `min_support` true flows), the lookback horizon H and the grace period.
4. Freeze thresholds and criteria, tag the commit, then run the test scenarios once.
5. **Primary endpoint:** change in warning lead time (onset window − first alert window) of
   M4 over M3, with bootstrap 95% confidence intervals across scenarios and seeds.
6. **Secondary:** missed degradation events, false alerts, class-wise recall/F1, detection
   coverage, compute overhead.
7. The hypothesis is supported **only if M4 beats M3 across repeated scenarios without test-label
   threshold tuning**. Otherwise we report the conditions of no benefit or extra false alarms.
   Negative results are valid results.

## 5. Experiments A–G (exactly as in the PDF)

| Exp | Description | Status |
|---|---|---|
| A | Baseline classifier with per-class precision/recall/F1 | **In progress for 17 Nov (validation only)** |
| B | Temporal-shift replay (natural chronological drift) | Phase 4 |
| C | Controlled shifts: covariate/scale, class-conditional, synthetic concept-shift proxy, no-degradation control | Phase 4 |
| D | SHAP window monitoring on a fixed sample per window | Phase 3–4 |
| E | Delayed-label replay (labels revealed after a fixed number of windows) | Phase 4 |
| F | Thresholds calibrated on validation to a common false-alarm budget; M3 vs M4 on identical test windows | Phase 4 |
| G | Ablation and sensitivity: window size, SHAP sampling fraction, random seeds (+ RQ3 axes) | Phase 5 |

Synthetic shifts (C) are always labelled synthetic. Natural drift (B) is preferred evidence where it exists.

## 6. Open research questions to settle

| ID | Question | When |
|---|---|---|
| D1 | Multi-class framing (ADR-0006) | Guide, Nov |
| D2 | Original vs corrected CIC-IDS2017 (ADR-0007) | Guide, Nov |
| — | Split strategy and evaluable classes (ADR-0008) | After audit, Nov |
| D3 | Window definition: fixed count vs fixed time | Phase 3 |
| D4 | Primary M4 distance (Kendall τ / L1 / JSD / PSI-on-SHAP), pre-registered | Phase 3 |
| D5 | How M3/M4 combine component scores (proposed: max of validation percentiles) | Phase 4 |
| D6 | Degradation criterion values δ, k, H, min_support | Phase 4, before test |
| — | Novelty statement after reading full texts of refs [1]–[4] | By Phase 5 |
