# ADR-0004: Label firewall between monitoring and evaluation

- **Status:** Accepted (approved plan §4: monitors see inputs, predictions, scores and SHAP values "but never labels")
- **Date:** 2026-11-06

## Context
RQ1 is only valid if monitors M1–M4 never see ground truth. In the delayed-label replay
(Experiment E) labels arrive late and must reach only the evaluator.

## Decision
The rule is enforced in three ways when the monitoring code is written (Phase 3):
1. **Types.** Monitors accept an `UnlabelledWindow` (features, scores, predicted class, SHAP
   sample) that has no label field. Labels live only in a `LabelLedger`, which releases them
   after `label_delay_windows`.
2. **Import contract.** import-linter forbids `eaidrs.monitor`, `eaidrs.explain`,
   `eaidrs.model` and `eaidrs.replay` from importing `eaidrs.evaluation`. The contract is added
   in the PR that creates those packages.
3. **Tests.** `UnlabelledWindow` contains no label column, and the ledger releases nothing early.

Until Phase 3 the same rule holds by construction: inference and SHAP functions take feature
matrices only, and the processed **test** split is written to a `sealed/` folder that loaders
refuse to read unless the caller explicitly allows it.

## Consequences
A small amount of extra typing. In return, the methodology section can point to code and CI
evidence instead of a promise.
