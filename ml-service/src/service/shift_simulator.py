from dataclasses import asdict, dataclass
from typing import List, Literal, Optional
import numpy as np
import pandas as pd
from sklearn.metrics import recall_score
from src.config import settings
from src.logger import get_logger
from src.service.model_engine import IDSEngine
from src.service.monitors import DriftMonitorSuite

logger = get_logger(__name__)

ShiftType = Literal[
    "none",               # Experiment B / No-degradation control
    "covariate_benign",   # Benign input drift (tests false-alarm resilience)
    "class_conditional",  # Attack feature scaling without changing label boundary
    "concept_proxy",      # Attack feature mutation causing silent recall degradation
]


@dataclass
class MonitorComparisonMetrics:
    monitor: str
    empirical_far_pct: float
    t_alarm: Optional[int]
    t_fail: Optional[int]
    lead_time_delta_t: Optional[int]
    missed_degradation: bool
    mean_score_post_shift: float


def inject_controlled_shift(
    X_win: np.ndarray,
    y_true: np.ndarray,
    target_attack: str,
    shift_type: ShiftType,
    severity: float,
    top_feature_indices: List[int],
    rng: np.random.Generator,
) -> np.ndarray:
    """Applies controlled shift regimes (Experiment C) in-place on a copy of X_win."""
    if shift_type == "none" or severity <= 0.0:
        return X_win

    X_mod = X_win.copy()
    cols = top_feature_indices[:6]

    if shift_type == "covariate_benign":
        b_rows = np.where(y_true == "BENIGN")[0]
        if len(b_rows) > 0:
            X_mod[np.ix_(b_rows, cols)] *= 1.0 + 0.35 * severity

    elif shift_type == "class_conditional":
        a_rows = np.where(y_true == target_attack)[0]
        if len(a_rows) > 0:
            X_mod[np.ix_(a_rows, cols)] *= 1.0 + 0.20 * severity

    elif shift_type == "concept_proxy":
        a_rows = np.where(y_true == target_attack)[0]
        if len(a_rows) > 0:
            noise = rng.normal(
                0.0, 1.5 * severity, size=(len(a_rows), len(cols))
            ).astype(np.float32)
            X_mod[np.ix_(a_rows, cols)] = (
                X_mod[np.ix_(a_rows, cols)] * (1.0 - 0.65 * severity) + noise
            )

    return X_mod


def bootstrap_ci(values: List[float], n_boot: int = 500, seed: int = 42) -> tuple[float, float]:
    """Computes 95% bootstrap confidence interval."""
    if not values:
        return (0.0, 0.0)
    arr = np.asarray(values, dtype=np.float64)
    rng = np.random.default_rng(seed)
    means = [
        float(np.mean(rng.choice(arr, size=len(arr), replace=True)))
        for _ in range(n_boot)
    ]
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def _locate_attack_window_range(
    test_df: pd.DataFrame,
    target_attack: str,
    window_size: int,
    pre_windows: int = 12,
    post_windows: int = 28,
) -> tuple[int, int, int]:
    """Finds the first chronological window containing target_attack and frames pre/post windows."""
    total_windows = len(test_df) // window_size
    first_atk_win: Optional[int] = None

    for w in range(total_windows):
        chunk_y = test_df.iloc[w * window_size : (w + 1) * window_size]["target"]
        if int((chunk_y == target_attack).sum()) >= 30:
            first_atk_win = w
            break

    if first_atk_win is None:
        return 0, min(12, total_windows), min(40, total_windows)

    start_win = max(0, first_atk_win - pre_windows)
    shift_start = first_atk_win + 4
    end_win = min(total_windows, shift_start + post_windows)
    return start_win, shift_start, end_win


def run_controlled_experiment(
    test_df: pd.DataFrame,
    feature_cols: List[str],
    engine: IDSEngine,
    monitor: DriftMonitorSuite,
    target_attack: str = "DDoS",
    shift_type: ShiftType = "concept_proxy",
    shift_start_window: Optional[int] = None,
    max_windows: int = 40,
    recall_cutoff: float = 0.80,
) -> dict:
    """
    Executes full delayed-label replay (Experiments B, C, E, F) anchored around the
    chronological arrival of target_attack in test_stream.parquet.
    """
    step = settings.WINDOW_SIZE
    total_windows = len(test_df) // step

    if shift_start_window is None:
        start_win, active_shift_start, end_win = _locate_attack_window_range(
            test_df, target_attack, step, pre_windows=12, post_windows=max(15, max_windows - 12)
        )
    else:
        start_win = 0
        active_shift_start = shift_start_window
        end_win = min(total_windows, max_windows)

    logger.info(
        "Running experiment | attack=%s | shift=%s | windows=%d..%d | shift_start=%d",
        target_attack,
        shift_type,
        start_win,
        end_win - 1,
        active_shift_start,
    )

    rng = np.random.default_rng(settings.RANDOM_SEED)
    window_records: List[dict] = []

    for w_id in range(start_win, end_win):
        chunk = test_df.iloc[w_id * step : (w_id + 1) * step]
        X_raw = chunk[feature_cols].to_numpy(dtype=np.float32)
        y_true = chunk["target"].to_numpy()

        severity = (
            min(1.0, (w_id - active_shift_start + 1) / 8.0)
            if w_id >= active_shift_start
            else 0.0
        )
        X_w = inject_controlled_shift(
            X_raw,
            y_true,
            target_attack=target_attack,
            shift_type=shift_type,
            severity=severity,
            top_feature_indices=monitor.ref.top_feature_indices,
            rng=rng,
        )

        # Label-free monitoring step
        probs, preds, shap_sub, shap_preds = engine.predict_and_explain(X_w, window_seed=w_id)
        res = monitor.evaluate_window(X_w, probs, shap_preds, shap_sub)

        # Delayed-label unlock step
        y_pred_str = engine.label_encoder.inverse_transform(preds)
        support = int(np.sum(y_true == target_attack))
        atk_recall = (
            float(recall_score(y_true == target_attack, y_pred_str == target_attack, zero_division=0))
            if support >= 10
            else None
        )

        window_records.append(
            {
                "window_id": w_id,
                "timestamp": str(chunk["timestamp"].iloc[0]) if "timestamp" in chunk.columns else None,
                "m1_score": res["m1_score"],
                "m2_score": res["m2_score"],
                "m3_score": res["m3_score"],
                "m4_score": res["m4_score"],
                "m1_alert": res["m1_alert"],
                "m2_alert": res["m2_alert"],
                "m3_alert": res["m3_alert"],
                "m4_alert": res["m4_alert"],
                "target_recall": atk_recall,
                "target_support": support,
            }
        )

    df_res = pd.DataFrame(window_records)
    post = df_res[df_res["window_id"] >= active_shift_start]
    pre = df_res[df_res["window_id"] < active_shift_start]

    fail_rows = post[post["target_recall"].notna() & (post["target_recall"] < recall_cutoff)]
    t_fail = int(fail_rows["window_id"].iloc[0]) if not fail_rows.empty else None

    comparisons: List[dict] = []
    for m in ["m1", "m2", "m3", "m4"]:
        alarms = post[post[f"{m}_alert"]]
        t_alarm = int(alarms["window_id"].iloc[0]) if not alarms.empty else None
        lead_time = (t_fail - t_alarm) if (t_fail is not None and t_alarm is not None) else None
        missed = bool(t_fail is not None and (t_alarm is None or t_alarm > t_fail))
        emp_far = float(pre[f"{m}_alert"].mean() * 100.0) if not pre.empty else 0.0
        mean_post = float(post[f"{m}_score"].mean()) if not post.empty else 0.0

        comparisons.append(
            asdict(
                MonitorComparisonMetrics(
                    monitor=m.upper(),
                    empirical_far_pct=round(emp_far, 2),
                    t_alarm=t_alarm,
                    t_fail=t_fail,
                    lead_time_delta_t=lead_time,
                    missed_degradation=missed,
                    mean_score_post_shift=round(mean_post, 4),
                )
            )
        )

    margin_vals = (post["m4_score"] - post["m3_score"]).tolist() if not post.empty else []
    ci_low, ci_high = bootstrap_ci(margin_vals, seed=settings.RANDOM_SEED)

    return {
        "target_attack": target_attack,
        "shift_type": shift_type,
        "shift_start_window": active_shift_start,
        "recall_cutoff": recall_cutoff,
        "t_fail": t_fail,
        "m4_minus_m3_margin_ci95": [round(ci_low, 4), round(ci_high, 4)],
        "monitor_comparison": comparisons,
        "windows": window_records,
    }