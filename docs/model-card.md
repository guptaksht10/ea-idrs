# Model Card: EA-IDRS baseline classifier

Status: **skeleton**. Filled from the MODEL-01/03/04 run folders and the model bundle
(DOC-04). Every metric is a **validation** metric; the test split stays sealed.

## 1. Model details

| Field | Value |
|---|---|
| Model family | Gradient-boosted trees: XGBoost and LightGBM (both trained; one selected) |
| Selected model | PENDING (chosen on validation by the criterion pre-declared in MODEL-02) |
| Task framing | Multi-class (benign + attack classes) with derived P(attack) = 1 − P(BENIGN) — **Proposed** (ADR-0006) |
| Bundle ID | PENDING |
| Git commit | PENDING |
| Data manifest hash | PENDING |
| Training split | PENDING (see data card §6) |
| Hyperparameters | PENDING (`configs/model/*.yaml`) |
| Class weighting | PENDING |
| Random seed | PENDING |
| Library versions | PENDING (from `bundle.json`) |

## 2. Intended use

Research baseline for the EA-IDRS study and the minor-evaluation demo. Not for production
network defence. Predictions never trigger automatic blocking.

## 3. Validation results (run `PENDING`)

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| PENDING | | | | |

Macro-F1: PENDING · Weighted-F1: PENDING · Attack-vs-benign recall / precision: PENDING.
XGBoost vs LightGBM comparison table: PENDING.

## 4. Explanations

SHAP TreeExplainer on raw (log-odds) model output. Explanations describe what drove **this
model's** prediction. They are not causal statements about the traffic.

## 5. Limitations

- Trained and validated on one testbed dataset (CIC-IDS2017).
- Rare classes have small support; their metrics are unstable.
- Validation metrics only. Test-split performance will be measured once, under the approved protocol.
