# ML service experiment log

Research question: does the explanation-aware monitor (M4) warn earlier than the
feature + score baseline (M3) before attack-class recall degrades, at a matched
false-alarm rate, when labels arrive late?

Run folders live in `artifacts/experiments/<run id>/` (gitignored; regenerate with
the commands in the README). Every run below was made on 2026-11-25 from a working
tree on top of commit `30dbf57` with uncommitted changes (`git_dirty: true`), so
each will be re-run from a clean commit before results are reported externally.

## Summary of versions

| Version | Run id | What changed | Why |
|---|---|---|---|
| v1 | `20261125T053626Z_grid_30dbf57` | first run of the frozen grid | baseline |
| v2 | `20261125T061911Z_grid_30dbf57` | monitor fixes (below) | code bugs found in an audit |
| v3 | `20261125T070325Z_grid_30dbf57` | split `per_class_temporal` -> `grouped_day_label` | calibration traffic did not look like test traffic |
| v4 | `20261125T075445Z_grid_30dbf57` | legacy shifts -> realistic, model-agnostic shifts | legacy shifts favoured M1 and made impossible values |
| v5 | `20261125T081817Z_grid_30dbf57` | geometric ramp; new evaluation | v4 recall collapsed in the first shifted window |
| dose | `20261125T081626Z_dose_response` | recall vs shift size, validation split | evidence for the v5 ramp |

v1 and v2 used the `per_class_temporal` split; their model and calibration artifacts
were overwritten by later runs.

## False alarms with no shift injected (whole test stream, calibrated thresholds, target 5%)

| Version | M1 | M2 | M3 | M4 | Notes |
|---|---|---|---|---|---|
| v1 | 2.6% | 30.6% | 27.7% | 26.3% | 494 windows |
| v2 | 0.2% | 30.4% | 17.6% | 18.6% | validation: 4.7% for all four (calibration works as designed) |
| v3 / v4 / v5 | 0.2% | 9.5% | 5.7% | 4.9% | benign-only windows: 0.0 / 5.5 / 2.3 / 1.6% |

## What each change fixed

**v2: monitor bugs.** (1) SHAP rows were bucketed by the first 512 window
predictions instead of the predictions of the explained flows. (2) The SHAP
reference explained only 512 random training flows (DDoS 22, PortScan 22, Bot and
WebAttack 0); it now explains up to 1,000 flows per predicted class. (3) M3/M4
added median-scaled signals, so one extreme signal swamped the rest; every signal
is now a conformal surprisal on one bounded scale. M2's own false alarms were not a
scaling bug: calibration used mostly Wednesday benign traffic while the test stream
was Thursday-Friday, and on Thursday afternoon the model labels 11% of "benign"
flows as attacks (the unlabelled port scan reported by Lanvin et al. 2022).

**v3: split.** Each (capture day, original label) group is cut 50/15/35 in capture
order, so every split has benign traffic from every day. Stream FAR for M3/M4
dropped from ~18% to ~5%. Validation macro-F1 rose from 0.936 to 0.974 because
validation now comes from the same days as training (less natural drift).

**v4: shifts.** Shifts act on named feature families with consistent physics
(slow-down scales times up and rates down; padding moves sizes, byte totals and
bytes/s together) and never touch port, flags, window sizes, header lengths or
packet counts. Recall degraded in 5 of 12 attack x shift cells (v3: 2), but always
in the first shifted window, so lead time was ~0 for every monitor.

**v5: ramp and evaluation.** The validation dose-response shows cliffs: padding
breaks DDoS and DoS between 8 and 16 bytes and PortScan between 4 and 8 bytes;
mimicry lowers PortScan recall smoothly from 0.99 to 0.23; slow-down barely matters
(DoS 0.96 at 10x). A geometric 20-window ramp from 1 byte places windows below each
cliff. Evaluation now uses the whole unshifted stream for FAR, compares monitors at
matched stream FAR (1/2/5/10%), defines degradation as a recall drop from the
clean-validation baseline (0.05-0.20; primary 0.15), and counts only alarms the
control run does not also raise.

## v5 results

Primary (pre-registered: matched 5% FAR, 0.15 recall drop): recall degraded in 9
runs (DDoS padding, DDoS mimicry x3, DoS padding, PortScan padding, PortScan
mimicry x3). M2, M3 and M4 warned in all 9, 6-13 windows before degradation; M1
warned in 1 (DoS padding) and missed the rest. **M4 and M3 tied in all 9.**

M4 vs M3 across all thresholds and criteria (`head_to_head.csv`): tie at the
calibrated and 5% thresholds; M3 earlier in 7-9 of 9 at 1-2% FAR; M4 earlier in 4
of 9 at 10% FAR. No consistent M4 advantage.

Why: M2 (output confidence) alarms in the first shifted window, even at 1 byte of
padding with recall still 1.000 (DDoS: M2 surprisal 1.37 in the control vs 5.36 in
the shifted run). Nothing can warn earlier than that, so M3 and M4, which both
contain M2, hit the same ceiling. At tight FAR budgets M4 averages M2 with two other
signals and is diluted, so M3 is earlier.

Benign slow-down and attack slow-down did not degrade recall and raised no extra
alarms.

### Exploratory (not pre-registered)

Without M2, the explanation signal (SHAP surprisal, recovered as 3*M4 - M1 - M2)
warned earlier than the feature signal (M1) in 8 of 9 degraded runs at matched 5%
FAR (1 tie) and 9 of 9 at 10% (`python -m src.service.explore_components <run>`).
At 1-2%, M1 cannot reach the target FAR (ties at its maximum score give 0.2%), so
those rows are not a fair comparison. With 9 runs from 5 attack x shift scenarios
(the three mimicry seeds are not independent), this is a hypothesis for a new,
pre-registered version, not a result.

## Status of the research question

Not supported so far: M4 does not warn earlier than M3 at a matched false-alarm
rate in any version. Supported so far: (a) label-free monitors that include model
confidence give 6-13 windows of warning before recall drops under padding and
mimicry; (b) the detector is fragile to small padding (8-16 bytes); (c)
exploratory, explanations warn earlier than raw features.

## Known limits

- Small sample: 3 attacks, 4 shifts, 9 degraded runs; single model and dataset.
- Shifts are synthetic; mimicry interpolates on 5 features, which can break
  consistency with untouched features.
- Matched-FAR thresholds use the (unlabelled) test stream; they are an evaluation
  analysis, not a deployable calibration.
- Thursday-afternoon "benign" traffic contains an unlabelled port scan; it is not
  relabelled yet (Engelen et al. 2021 provide corrected labels).
- Time order is file row order; the clean data's timestamps are reconstructed.
