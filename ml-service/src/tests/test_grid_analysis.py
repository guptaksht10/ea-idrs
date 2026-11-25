import numpy as np
import pandas as pd
import pytest
from src.service import grid_analysis as ga


def _run(attack, shift, seed, recalls, m3_alerts, m4_alerts, start=0):
    n = len(recalls)
    df = pd.DataFrame(
        {
            "attack": attack, "shift_type": shift, "seed": seed, "window_id": range(start, start + n),
            "target_recall": recalls,
            "m1_alert": False, "m2_alert": False, "m3_alert": m3_alerts, "m4_alert": m4_alerts,
        }
    )
    for m in ga.MONITORS:
        df[f"{m}_score"] = df[f"{m}_alert"].astype(float)
    return df


def test_degradation_is_measured_against_the_validation_baseline():
    run = _run("DDoS", "x", 1, [0.99, 0.95, 0.90, 0.84, 0.70], [False] * 5, [False] * 5)
    assert ga.first_degradation(run, 0, "drop_0.15", baseline_recall=0.99) == 3
    assert ga.first_degradation(run, 0, "drop_0.05", baseline_recall=0.99) == 2
    assert ga.first_degradation(run, 0, "abs_0.80", baseline_recall=0.99) == 4
    assert ga.first_degradation(run, 4, "drop_0.20", baseline_recall=0.99) == 4
    assert ga.first_degradation(run, 0, "drop_0.15", baseline_recall=0.80) is None


def test_alarms_also_raised_in_the_control_run_do_not_count():
    # shift starts at window 2; recall degrades at window 5
    control = _run("DDoS", "none", 1, [1.0] * 7, [False, False, True, False, False, False, False], [False] * 7)
    shifted = _run(
        "DDoS", "attack_padding", 1, [1.0, 1.0, 1.0, 1.0, 0.95, 0.5, 0.4],
        m3_alerts=[False, False, True, False, False, True, True],   # window 2 is a natural alarm
        m4_alerts=[False, False, False, True, True, True, True],
    )
    windows = pd.concat([control, shifted])
    starts = {("DDoS", "none", 1): 2, ("DDoS", "attack_padding", 1): 2}
    leads = ga.lead_time_table(windows, starts, {"DDoS": 1.0}, thresholds={})
    row = lambda m: leads[(leads.shift_type == "attack_padding") & (leads.monitor == m)
                          & (leads.criterion == "drop_0.15")].iloc[0]
    assert row("M3")["t_alarm_raw"] == 2 and row("M3")["t_alarm"] == 5
    assert row("M3")["lead_time"] == 0 and not row("M3")["missed"]
    assert row("M4")["t_alarm"] == 3 and row("M4")["lead_time"] == 2

    h2h = ga.head_to_head(leads)
    primary = h2h[(h2h.threshold == "calibrated") & (h2h.criterion == "drop_0.15")].iloc[0]
    assert primary["M4 earlier"] == 1 and primary["degraded_runs"] == 1


def test_a_warning_after_degradation_is_a_miss():
    control = _run("DoS", "none", 1, [1.0] * 4, [False] * 4, [False] * 4)
    shifted = _run("DoS", "attack_mimicry", 1, [1.0, 0.5, 0.5, 0.5], [False, False, True, True], [False] * 4)
    leads = ga.lead_time_table(
        pd.concat([control, shifted]), {("DoS", "none", 1): 0, ("DoS", "attack_mimicry", 1): 0}, {"DoS": 1.0}, {}
    )
    r = leads[(leads.shift_type == "attack_mimicry") & (leads.monitor == "M3") & (leads.criterion == "drop_0.15")]
    assert r.iloc[0]["missed"] and pd.isna(r.iloc[0]["lead_time"])


def test_matched_far_thresholds_never_exceed_the_target_rate():
    rng = np.random.default_rng(0)
    stream = pd.DataFrame({f"{m}_score": rng.exponential(size=500) for m in ga.MONITORS})
    stream["m1_score"] = np.round(stream["m1_score"], 1)  # ties
    thresholds = ga.matched_far_thresholds(stream, fars=[0.01, 0.05])
    achieved = ga.achieved_far(stream, thresholds)
    for far in (0.01, 0.05):
        sel = achieved[achieved.threshold == f"far_{far:.2f}"]
        assert (sel["achieved_far_pct"] <= 100 * far + 1e-9).all()
        assert (sel[sel.monitor != "M1"]["achieved_far_pct"] >= 100 * far - 0.5).all()


def test_shap_signal_is_recovered_from_saved_scores():
    from src.service.explore_components import add_shap_signal

    df = pd.DataFrame({"m1_score": [1.0], "m2_score": [2.0], "m4_score": [(1.0 + 2.0 + 0.5) / 3.0]})
    assert add_shap_signal(df)["shap_score"].iloc[0] == pytest.approx(0.5)
