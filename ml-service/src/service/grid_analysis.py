"""Evaluation of grid runs (v5): false-alarm rates, matched-FAR thresholds, degradation and lead times.

Replay produces label-free monitor scores per window; this module evaluates them afterwards.
Labels are only used here, through `target_recall`, to find when recall degraded.

Definitions (fixed 2026-11-25 before any v5 result was seen):
- Stream FAR: share of windows of the whole unshifted test stream on which a monitor alarms.
- Matched-FAR threshold: per monitor, the score above which exactly at most `far` of the unshifted
  test-stream windows alarm. Comparing monitors at the same `far` makes their false-alarm cost
  equal. It uses no labels, but it does use the test stream, so it is an evaluation analysis,
  not a deployable calibration; the calibrated thresholds (from validation) are reported too.
- Degradation (t_fail): first window at or after the shift start whose target-attack recall is at
  least `drop` below the attack's clean-validation recall (the API's /unlock-labels rule).
  The legacy absolute rule (recall < 0.80) is reported for continuity.
- Attributable alarm (t_alarm): first window at or after the shift start where the monitor alarms
  and the same monitor did NOT alarm on that window in the unshifted control run. Without this,
  a natural alarm that happens near the shift start would count as an early warning.
- Lead time = t_fail - t_alarm. A warning must come no later than t_fail, otherwise it is missed.
"""

from typing import Dict, List, Optional, Sequence
import numpy as np
import pandas as pd
from src.config import settings
from src.service.model_engine import IDSEngine
from src.service.monitors import DriftMonitorSuite

MONITORS = ["m1", "m2", "m3", "m4"]
MATCHED_FARS = [0.01, 0.02, 0.05, 0.10]
RECALL_DROPS = [0.05, 0.10, 0.15, 0.20]
LEGACY_ABS_CUTOFF = 0.80
PRIMARY = {"threshold": "far_0.05", "criterion": "drop_0.15"}


def score_stream(
    test_df: pd.DataFrame, feature_cols: List[str], engine: IDSEngine, monitor: DriftMonitorSuite
) -> pd.DataFrame:
    """Scores every full window of the unshifted test stream, exactly as the replay does (same seeds)."""
    step = settings.WINDOW_SIZE
    rows = []
    for w_id in range(len(test_df) // step):
        chunk = test_df.iloc[w_id * step : (w_id + 1) * step]
        X = chunk[feature_cols].to_numpy(dtype=np.float32)
        probs, _, shap_sub, shap_preds = engine.predict_and_explain(X, window_seed=w_id)
        res = monitor.evaluate_window(X, probs, shap_preds, shap_sub)
        rows.append(
            {
                "window_id": w_id,
                "benign_only": bool((chunk["target"] == "BENIGN").all()),
                **{f"{m}_score": res[f"{m}_score"] for m in MONITORS},
                **{f"{m}_alert": res[f"{m}_alert"] for m in MONITORS},
            }
        )
    return pd.DataFrame(rows)


def stream_false_alarm_rates(stream: pd.DataFrame) -> pd.DataFrame:
    benign = stream[stream["benign_only"]]
    return pd.DataFrame(
        [
            {
                "monitor": m.upper(),
                "windows": len(stream),
                "far_all_pct": round(100.0 * stream[f"{m}_alert"].mean(), 2),
                "benign_only_windows": len(benign),
                "far_benign_only_pct": round(100.0 * benign[f"{m}_alert"].mean(), 2) if len(benign) else np.nan,
            }
            for m in MONITORS
        ]
    )


def matched_far_thresholds(stream: pd.DataFrame, fars: Sequence[float] = MATCHED_FARS) -> Dict[str, Dict[str, float]]:
    """{"far_0.05": {"m1": thr, ...}, ...}; alarm when score > thr, so the stream FAR is <= far."""
    out: Dict[str, Dict[str, float]] = {}
    for far in fars:
        out[f"far_{far:.2f}"] = {
            m: float(np.quantile(stream[f"{m}_score"].to_numpy(), 1.0 - far, method="higher")) for m in MONITORS
        }
    return out


def achieved_far(stream: pd.DataFrame, thresholds: Dict[str, Dict[str, float]]) -> pd.DataFrame:
    """Actual stream FAR of each matched threshold (ties at the top can make it lower than the target)."""
    rows = []
    for source, thr in thresholds.items():
        for m in MONITORS:
            rows.append(
                {
                    "threshold": source,
                    "monitor": m.upper(),
                    "score_threshold": round(thr[m], 4),
                    "achieved_far_pct": round(100.0 * float((stream[f"{m}_score"] > thr[m]).mean()), 2),
                }
            )
    return pd.DataFrame(rows)


def first_degradation(run: pd.DataFrame, shift_start: int, criterion: str, baseline_recall: float) -> Optional[int]:
    post = run[(run["window_id"] >= shift_start) & run["target_recall"].notna()]
    if criterion == "abs_0.80":
        failed = post["target_recall"] < LEGACY_ABS_CUTOFF
    else:
        drop = float(criterion.split("_")[1])
        failed = (baseline_recall - post["target_recall"]) >= drop - 1e-12
    hits = post.loc[failed, "window_id"]
    return int(hits.iloc[0]) if not hits.empty else None


def _alarm_windows(run: pd.DataFrame, monitor: str, threshold: Optional[float]) -> set:
    flags = run[f"{monitor}_alert"] if threshold is None else run[f"{monitor}_score"] > threshold
    return set(run.loc[flags.astype(bool), "window_id"].astype(int))


def lead_time_table(
    windows: pd.DataFrame,
    shift_starts: Dict[tuple, int],
    baseline_recalls: Dict[str, float],
    thresholds: Dict[str, Dict[str, float]],
    control_shift: str = "none",
) -> pd.DataFrame:
    """
    One row per (run, monitor, threshold source, degradation criterion).
    windows: windows.csv rows with attack, shift_type, seed, window_id, m*_score, m*_alert, target_recall.
    shift_starts: {(attack, shift_type, seed): shift_start_window}.
    """
    sources: Dict[str, Optional[Dict[str, float]]] = {"calibrated": None, **thresholds}
    criteria = [f"drop_{d:.2f}" for d in RECALL_DROPS] + [f"abs_{LEGACY_ABS_CUTOFF:.2f}"]
    rows = []
    for (attack, shift, seed), run in windows.groupby(["attack", "shift_type", "seed"], sort=False):
        start = shift_starts[(attack, shift, seed)]
        control = windows[(windows["attack"] == attack) & (windows["shift_type"] == control_shift)]
        control = control[control["seed"] == control["seed"].min()]
        for source, thr in sources.items():
            for m in MONITORS:
                thr_m = None if thr is None else thr[m]
                alarms = _alarm_windows(run, m, thr_m)
                natural = _alarm_windows(control, m, thr_m)
                post_alarms = sorted(w for w in alarms if w >= start)
                attributable = [w for w in post_alarms if w not in natural]
                t_alarm = attributable[0] if attributable else None
                for crit in criteria:
                    t_fail = first_degradation(run, start, crit, baseline_recalls.get(attack, 1.0))
                    warned = t_fail is not None and t_alarm is not None and t_alarm <= t_fail
                    rows.append(
                        {
                            "attack": attack, "shift_type": shift, "seed": seed, "shift_start": start,
                            "monitor": m.upper(), "threshold": source, "criterion": crit,
                            "t_fail": t_fail, "t_alarm": t_alarm,
                            "t_alarm_raw": post_alarms[0] if post_alarms else None,
                            "lead_time": (t_fail - t_alarm) if warned else None,
                            "missed": bool(t_fail is not None and not warned),
                        }
                    )
    return pd.DataFrame(rows)


def head_to_head(leads: pd.DataFrame, a: str = "M4", b: str = "M3") -> pd.DataFrame:
    """Per threshold source and criterion, over runs where recall degraded: does `a` warn earlier than `b`?"""
    key = ["attack", "shift_type", "seed", "threshold", "criterion"]
    deg = leads[leads["t_fail"].notna()]
    pa = deg[deg["monitor"] == a].set_index(key)["lead_time"]
    pb = deg[deg["monitor"] == b].set_index(key)["lead_time"]
    joined = pd.concat({a: pa, b: pb}, axis=1)
    # a missed warning counts as infinitely late
    la, lb = joined[a].fillna(-np.inf), joined[b].fillna(-np.inf)
    joined["outcome"] = np.where(la > lb, f"{a} earlier", np.where(la < lb, f"{b} earlier", "tie"))
    counts = joined.groupby(["threshold", "criterion", "outcome"]).size().unstack("outcome", fill_value=0)
    for col in (f"{a} earlier", "tie", f"{b} earlier"):
        if col not in counts:
            counts[col] = 0
    counts["degraded_runs"] = counts[[f"{a} earlier", "tie", f"{b} earlier"]].sum(axis=1)
    return counts[[f"{a} earlier", "tie", f"{b} earlier", "degraded_runs"]].reset_index()
