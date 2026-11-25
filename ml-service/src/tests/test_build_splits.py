import numpy as np
import pandas as pd
import pytest
from src.preprocessing.build_splits import split_frame


def _week() -> pd.DataFrame:
    """Day 0 benign only; day 1 benign + DoS Hulk; day 2 benign + DDoS (rows in capture order)."""
    rows = []
    for day, groups in {0: {"BENIGN": 100}, 1: {"BENIGN": 60, "DoS Hulk": 40}, 2: {"BENIGN": 50, "DDoS": 30}}.items():
        labels = [lab for lab, n in groups.items() for _ in range(n)]
        order = np.random.default_rng(day).permutation(len(labels))  # interleave labels within the day
        for row_order, idx in enumerate(order):
            rows.append({"day_order": day, "row_order": row_order, "Label": labels[idx]})
    df = pd.DataFrame(rows)
    df["target"] = df["Label"].replace({"DoS Hulk": "DoS"})
    return df


def test_grouped_day_label_puts_every_day_and_label_in_every_split():
    train, val, test = split_frame(_week(), "grouped_day_label", 0.5, 0.2)
    groups = set(_week().groupby(["day_order", "Label"]).groups)
    for part in (train, val, test):
        assert set(part.groupby(["day_order", "Label"]).groups) == groups
    # benign from every day in validation, so calibration sees the same days as the test stream
    assert set(val.loc[val["Label"] == "BENIGN", "day_order"]) == {0, 1, 2}


def test_grouped_split_is_chronological_within_each_group_and_disjoint():
    train, val, test = split_frame(_week(), "grouped_day_label", 0.5, 0.2)
    key = ["day_order", "row_order"]
    ids = [set(map(tuple, p[key].to_numpy())) for p in (train, val, test)]
    assert not (ids[0] & ids[1] or ids[0] & ids[2] or ids[1] & ids[2])
    assert sum(len(i) for i in ids) == len(_week())
    for (day, label), _ in _week().groupby(["day_order", "Label"]):
        sel = [p[(p["day_order"] == day) & (p["Label"] == label)]["row_order"] for p in (train, val, test)]
        assert sel[0].max() < sel[1].min() and sel[1].max() < sel[2].min()
    for p in (train, val, test):
        assert p[key].equals(p.sort_values(key)[key].reset_index(drop=True))


def test_per_class_mode_keeps_original_behaviour():
    train, val, test = split_frame(_week(), "per_class_temporal", 0.5, 0.2)
    # benign is cut across the whole week: early-day benign never reaches test, late-day never train
    benign_days = [set(p.loc[p["Label"] == "BENIGN", "day_order"]) for p in (train, val, test)]
    assert 0 not in benign_days[1] | benign_days[2]
    assert 2 not in benign_days[0]


def test_bad_split_settings_are_rejected():
    with pytest.raises(ValueError, match="Unknown split mode"):
        split_frame(_week(), "random", 0.5, 0.2)
    with pytest.raises(ValueError):
        split_frame(_week(), "grouped_day_label", 0.7, 0.4)
