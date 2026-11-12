# ADR-0006: Multi-class classifier with derived attack probability (decision D1)

- **Status:** **Proposed: requires guide confirmation**
- **Date:** 2026-11-06

## Context
Older documents framed detection as binary (benign vs malicious). The approved plan needs
per-class precision/recall/F1 (Experiment A), monitors the *predicted class mix* (M2), and
groups SHAP attributions *by predicted class* (M4). A binary model cannot produce a predicted
attack class.

## Decision (proposed)
Train a multi-class gradient-boosted tree on benign plus the attack classes present in
training. Derive `P(attack) = 1 − P(BENIGN)` for score monitoring and alerting. Report both
per-class metrics and derived binary attack-vs-benign metrics on validation.

If the class-by-split audit shows too little support, rare classes may be grouped into families
(for example, the three web attacks). Grouping is a config option (`label_groups` in the dataset
config) and is recorded in the data card.

## Consequences
Meets all three PDF requirements. Class imbalance needs class weights. SHAP for a multi-class
model returns one attribution vector per class; explanations show the predicted class.
