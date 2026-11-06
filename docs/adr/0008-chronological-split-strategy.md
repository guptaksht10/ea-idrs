# ADR-0008: Chronological split strategy

- **Status:** **Proposed: decide after the class-by-time audit (Nov 9) with the guide**
- **Date:** 2026-11-06

## Context
The approved plan requires chronological train / validation / test splits. CIC-IDS2017 is a
five-day capture in which most attack types occur on a **single day**, often within minutes.
A split by day (older plan: Mon–Wed train, Thu validation, Fri test) is therefore expected to
leave the Thursday and Friday attack classes (web attacks, infiltration, bot, port scan, DDoS)
absent from training. A class the model never saw cannot show "recall degradation", so RQ1
could then be studied only on the classes present in all three splits.
**This expectation must be checked on the actual files, not assumed.**

## Options (both implemented in `eaidrs.data.splits`)
1. **`global_time`**: one global timeline cut at two timestamps
   (`configs/split/global_by_day.yaml`: Mon–Wed / Thu / Fri). Purely "the earlier segment trains".
2. **`grouped_time`**: within each (day, label) group, the earliest ~60% of flows train, the next
   ~20% validate, and the latest ~20% test (`configs/split/grouped_by_day_label.yaml`). Cuts are
   placed between distinct timestamps, so no timestamp appears in two splits of the same group.

## Decision
Pending. Ankit runs `eaidrs audit` with both configs on the real data and takes the
class-by-split tables to the guide. Selection rule, fixed in advance:
prefer `global_time` if the classes needed for a meaningful RQ1 study have at least
`min_class_support` flows in all three splits; otherwise use `grouped_time` and state the
trade-off in the report.

## Consequences
- `grouped_time` gives every class train/val/test support but weakens natural temporal drift
  between splits. Experiment B (temporal replay) evidence will then be modest, and
  Experiment C (controlled shifts) will carry more of RQ1.
- `global_time` keeps realistic drift but may leave too few evaluable classes.
- Whichever is chosen, the split boundaries, per-class counts and the reason go in the data card.
