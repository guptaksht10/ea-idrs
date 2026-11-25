import pandas as pd

from src.service.report import _pct, _spread, results_table


def _row(shift, seed, monitor, t_fail, lead):
    return {"attack": "DDoS", "shift_type": shift, "seed": seed, "monitor": monitor,
            "threshold": "far_0.05", "criterion": "drop_0.15", "t_fail": t_fail, "lead_time": lead}


def test_results_table_formats_seeds_missed_and_not_degraded():
    rows = []
    for seed in (42, 43, 44):
        rows += [_row("attack_mimicry", seed, "M1", 470, None)]
        rows += [_row("attack_mimicry", seed, m, 470, 10 + seed - 42) for m in ("M2", "M3", "M4")]
    rows += [_row("attack_low_rate", 42, m, None, None) for m in ("M1", "M2", "M3", "M4")]
    rows += [_row("none", 42, "M1", None, None)]  # control run is not a scenario
    # Non-primary rows must be ignored.
    rows += [{**_row("attack_mimicry", 42, "M2", 470, 99), "threshold": "far_0.10"}]

    table = results_table(pd.DataFrame(rows)).set_index("shift")

    assert list(table.index) == ["mimicry", "low rate"]
    assert table.loc["mimicry", "degraded"] == 3
    assert table.loc["mimicry", "M1"] == "missed"
    assert table.loc["mimicry", "M2"] == "11.0 ± 1.0"
    assert table.loc["low rate", "degraded"] == 0
    assert table.loc["low rate", "M4"] == "–"


def test_helpers():
    assert _pct("far_0.05") == "5%"
    assert _pct("far_0.10") == "10%"
    spread = _spread({"a": 0.30, "b": 0.31, "c": 0.90}, gap=0.1)
    assert spread["b"] - spread["a"] >= 0.1 - 1e-12
    assert spread["c"] == 0.90
