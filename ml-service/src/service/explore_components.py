"""EXPLORATORY analysis (not pre-registered): does the explanation signal warn earlier than features?

Grid v5 showed a ceiling effect: M2 (model confidence) alarms in the first shifted window, so M3 and
M4 (which both contain M2) tie. This compares the two signals that differ between M3 and M4 without
M2: the feature signal (M1) and the class-conditional SHAP signal. The SHAP surprisal is recovered
from saved scores as 3*M4 - M1 - M2 (scores are stored to 4 decimals). Same evaluation rules as
grid_analysis: matched stream FAR, 0.15 recall drop, alarms attributable to the shift only.

Treat results as hypothesis-generating; test them in a new, pre-registered grid version.

Usage (from ml-service/):
    python -m src.service.explore_components artifacts/experiments/<grid run id>
"""

import json
from pathlib import Path
import sys
from typing import Dict
import numpy as np
import pandas as pd
from src.service import grid_analysis as ga

SIGNALS = ["m1", "shap"]


def add_shap_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["shap_score"] = 3.0 * df["m4_score"] - df["m1_score"] - df["m2_score"]
    return df


def component_leads(
    windows: pd.DataFrame, stream: pd.DataFrame, baseline_recalls: Dict[str, float], criterion: str = "drop_0.15"
) -> pd.DataFrame:
    windows, stream = add_shap_signal(windows), add_shap_signal(stream)
    rows = []
    for far in ga.MATCHED_FARS:
        thr = {m: float(np.quantile(stream[f"{m}_score"], 1.0 - far, method="higher")) for m in SIGNALS}
        achieved = {m: round(100.0 * float((stream[f"{m}_score"] > thr[m]).mean()), 2) for m in SIGNALS}
        for (attack, shift, seed), run in windows.groupby(["attack", "shift_type", "seed"], sort=False):
            if shift == "none":
                continue
            start = int(run["shift_start_window"].iloc[0])
            t_fail = ga.first_degradation(run, start, criterion, baseline_recalls[attack])
            if t_fail is None:
                continue
            control = windows[(windows["attack"] == attack) & (windows["shift_type"] == "none")]
            row = {"far": far, "attack": attack, "shift_type": shift, "seed": seed, "t_fail_after_start": t_fail - start}
            for m in SIGNALS:
                natural = set(control.loc[control[f"{m}_score"] > thr[m], "window_id"])
                alarms = [w for w in run.loc[run[f"{m}_score"] > thr[m], "window_id"] if w >= start and w not in natural]
                t_alarm = alarms[0] if alarms else None
                row[f"{m}_lead"] = (t_fail - t_alarm) if (t_alarm is not None and t_alarm <= t_fail) else None
                row[f"{m}_achieved_far_pct"] = achieved[m]
            rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    shap_l, m1_l = out["shap_lead"].fillna(-np.inf), out["m1_lead"].fillna(-np.inf)
    out["outcome"] = np.where(shap_l > m1_l, "SHAP earlier", np.where(shap_l < m1_l, "M1 earlier", "tie"))
    return out


def main(run_dir: Path) -> None:
    windows = pd.read_csv(run_dir / "windows.csv")
    stream = pd.read_csv(run_dir / "stream_scores.csv")
    baselines = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))["baseline_recalls"]
    result = component_leads(windows, stream, baselines)
    result.to_csv(run_dir / "exploratory_shap_vs_m1.csv", index=False)
    print(result.groupby(["far", "outcome"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main(Path(sys.argv[1]))
