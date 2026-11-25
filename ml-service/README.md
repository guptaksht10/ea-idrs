# EA-IDRS ML service

XGBoost intrusion detector with TreeSHAP explanations, four label-free drift
monitors (M1-M4), a controlled shift simulator and a FastAPI service.

Research question: does the explanation-aware monitor (M4) warn earlier than
the feature + score baseline (M3) before attack-class recall degrades, at a
matched false-alarm rate, when labels arrive late?

| Monitor | Signal |
|---|---|
| M1 | Feature drift: mean KS statistic over the top-15 features |
| M2 | Output-score drift: Wasserstein distance on entropy and max confidence |
| M3 | Baseline composite: M1 + M2 |
| M4 | Explanation-aware: M1 + M2 + class-conditional TreeSHAP Wasserstein shift |

Scoring (v2): each raw signal is converted to a surprisal, `-ln(p)`, where `p`
is its conformal p-value against the clean validation windows. All signals then
share one bounded scale (0 to `ln(n+1)`), so no single signal can swamp a
composite. M3 and M4 are the mean surprisal of their signals. Every threshold is
the 95th percentile of that monitor's leave-one-out calibration scores (target
false-alarm rate 5%, matched across monitors).

The M4 reference explains up to 1,000 training flows per predicted class
(`SHAP_REFERENCE_PER_CLASS`), so rare classes such as Bot get a usable bucket.
Windows explain a random 512-flow subsample; each SHAP row is bucketed by the
prediction of the flow it explains (`preds_sub`).

## Setup

```bash
cd ml-service
uv sync
```

Put the 8 CIC-IDS2017 CSVs in `data/raw/` (gitignored). Both releases work:
`MachineLearningCVE` and `TrafficLabelling` (identifier columns and blank rows
are dropped during cleaning, so both give the same 2,827,876 clean rows).

## Pipeline

```bash
uv run python -m src.preprocessing.clean_cicids     # -> data/processed/cicids2017_clean.parquet
uv run python -m src.preprocessing.build_splits     # -> data/processed/splits/*.parquet
uv run python -m src.service.train_and_calibrate    # -> artifacts/ (model, reference, thresholds)
uv run python -m src.service.dose_response          # -> artifacts/experiments/<run_id>_dose_response/
uv run python -m src.service.run_grid               # -> artifacts/experiments/<run_id>/
uv run python -m src.service.report [<run_id>]      # -> <run_id>/report/ (results.md + figures; latest run by default)
```

Settings (split, window size, top-K features, calibration percentile) live in `src/config.py`.

## Split

`SPLIT_MODE = "grouped_day_label"` (default): every (capture day, original label)
group, e.g. (Monday, BENIGN) or (Wednesday, DoS Hulk), is cut in capture order:
earliest 50% train, next 15% clean validation, last 35% test. Each split is then
put back in capture order.

- Every split holds benign traffic from every day and every attack variant, so
  the validation windows used for calibration look like the test stream.
- Within a group, no flow is trained on after a flow it is tested on. Across days
  this is not a single time cut: training also sees early Friday traffic. This is
  needed because most attacks happen on one day only.
- Time order is `row_order` within each day (the clean data's `timestamp` column is
  reconstructed and evenly spaced, so it is not real capture time).

`per_class_temporal` (the original design, used by grid v1/v2) cuts each model class
across the whole week, so benign ends up Mon-Wed train / Wed-Thu val / Thu-Fri test.
`strict_day` is Mon-Wed / Thu-AM / Thu-PM-Fri.

## Experiment grid (frozen 2026-11-25)

Fixed before any grid result was seen. Do not change it to improve results;
add a new version instead and report both.

| Version | Grid | Monitors |
|---|---|---|
| `v1-2026-11-25` | as below | original: median scaling, SHAP rows bucketed by the wrong predictions, 512-flow SHAP reference |
| `v2-2026-11-25` | same | fixed: aligned SHAP buckets, class-stratified SHAP reference, conformal surprisal scoring |
| `v3-2026-11-25` | same | v2 monitors; split changed from `per_class_temporal` to `grouped_day_label` |
| `v4-2026-11-25` | new shifts (below) | v3 split and monitors; legacy shifts replaced by realistic shifts |
| `v5-2026-11-25` | v4 shifts, geometric ramp | v4 setup; new evaluation (below): stream FAR, matched FAR, baseline-relative degradation, attributable alarms |

v1-v3 used the legacy shifts `covariate_benign`, `class_conditional` and
`concept_proxy`. They act on the model's top-6 features (the features M1 watches)
and can create impossible values (for example `Destination Port` 80 -> 108). They
remain available for reproducing old runs.

### Shifts (v4, fixed before any v4 result was seen)

Defined in `src/service/shifts.py`. Shifts act on named feature families, never
on feature importance, the monitors' tracked features or SHAP values. Related
features move together, and port, flags, TCP window sizes, header lengths and
packet counts never change. Severity ramp: see v5 below (v4 used a linear ramp
over 8 windows).

| Shift | Rows | Change at full severity | Expectation |
|---|---|---|---|
| `none` | - | nothing (control) | no recall drop; alarms are false alarms |
| `benign_slowdown` | benign | durations and IATs x2, rates /2 | no recall drop; alarms are false alarms |
| `attack_low_rate` | target attack | durations and IATs x10, rates /10 | may lower recall |
| `attack_padding` | target attack | +256 bytes per packet; size features, fwd byte total and bytes/s updated | may lower recall |
| `attack_mimicry` | target attack | 90% of the way to a random real benign flow on the attack's 5 features with the largest KS distance to benign (validation split) | should lower recall |

The mimicry features and donor pool come from the clean validation split; both are
written to each run's `config.json` (`shift_spec`). Question under test (the research
question): when an attack changes how it looks, does M4 warn earlier than M3 before
recall drops, at a matched false-alarm rate?
Every shift is reported, including the ones where M4 is not expected to help.

- Attacks: DDoS, DoS, PortScan
- Shifts (v4+): `none`, `benign_slowdown`, `attack_low_rate`, `attack_padding`, `attack_mimicry`
- Seeds: 42, 43, 44 for `attack_mimicry` (the only random shift); other shifts run once
- 21 runs, 40 windows of 2,000 flows each (12 before the shift start, 28 from it)

### Ramp and evaluation (v5, fixed before any v5 result was seen)

v4 showed recall collapsing in the first shifted window, leaving no time for any
early warning. The dose-response on the validation split
(`python -m src.service.dose_response`, model only, no monitors) explains why:
recall responds to shift size over orders of magnitude, with cliffs (padding breaks
DDoS and DoS between 8 and 16 bytes, PortScan between 4 and 8 bytes). A linear ramp
jumps past every cliff in its first step.

- Ramp: geometric over 20 windows, from 1/256 of the full shift (1 byte of padding)
  to the full shift, a constant growth factor per window. 20 windows fit every
  attack (DDoS, the shortest, has 21 windows with >= 10 flows after the shift start).
  Padding is applied in whole bytes.
- Stream FAR: alarm rate on every window of the whole unshifted test stream
  (~500 windows), reported for all windows and for benign-only windows.
- Matched FAR: per monitor, the score threshold that alarms on at most 1%, 2%, 5%
  or 10% of the unshifted test stream. M3 and M4 are compared at the same rate.
  This uses no labels but does use the test stream, so it is an evaluation analysis,
  not a deployable calibration; calibrated (validation) thresholds are reported too.
- Degradation (t_fail): first window from the shift start whose target recall is at
  least 0.05 / 0.10 / 0.15 / 0.20 below the attack's clean-validation recall (the
  API's `/unlock-labels` rule); the legacy `recall < 0.80` is reported as well.
- Attributable alarm (t_alarm): first window from the shift start where the monitor
  alarms and did not alarm on the same window in the unshifted control run.
- Lead time = t_fail - t_alarm; a warning after t_fail is a miss.
- Primary result: matched 5% stream FAR and a 0.15 recall drop. All other
  threshold/criterion combinations are reported as a sensitivity analysis
  (`head_to_head.csv`: M4 earlier / tie / M3 earlier over degraded runs).

Monitors never see labels; labels are used only afterwards to find t_fail.
Definitions live in `src/service/grid_analysis.py`.

Each run folder holds `config.json` (grid, ramp, shift spec, baselines, git commit,
thresholds), `windows.csv` (every replayed window), `stream_scores.csv`,
`stream_far.csv`, `matched_far.csv`, `lead_times.csv`, `head_to_head.csv`,
`summary.md`, and the legacy `results.csv` / `summary.csv` (recall < 0.80,
calibrated thresholds, 16 pre-shift windows).

## API

```bash
uv run uvicorn src.service.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/docs`. Endpoints: `/health`, `/baseline-metrics`,
`/run-experiment`, `/evaluate-window`, `/replay-test-window/{window_id}`,
`/unlock-labels`. Needs the artifacts from `train_and_calibrate`.

## Tests

```bash
uv run pytest
```
