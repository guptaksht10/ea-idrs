import json
import numpy as np
import pandas as pd
import pytest
from src.config import settings
from src.service import run_grid as grid
from src.service.model_engine import IDSEngine
from src.service.monitors import DriftMonitorSuite, ReferenceProfile
from src.service.shifts import build_shift_context

N_FEATURES = 10
FEATURES = [f"f_{i}" for i in range(N_FEATURES)]


def _make_rows(rng: np.random.Generator, labels: list[str]) -> np.ndarray:
    X = rng.normal(0, 1, size=(len(labels), N_FEATURES)).astype(np.float32)
    labels_arr = np.asarray(labels)
    X[labels_arr == "DDoS", 0] += 3.0
    X[labels_arr == "DoS", 1] += 3.0
    return X


@pytest.fixture()
def tiny_setup(monkeypatch):
    monkeypatch.setattr(settings, "WINDOW_SIZE", 100)
    rng = np.random.default_rng(0)

    y_train = ["BENIGN"] * 300 + ["DDoS"] * 150 + ["DoS"] * 150
    X_train = _make_rows(rng, y_train)
    engine = IDSEngine(shap_sample_size=64, random_state=42)
    engine.fit(X_train, np.asarray(y_train), FEATURES)

    probs, preds, shap_sub, preds_sub = engine.predict_and_explain(X_train, window_seed=1)
    ref = ReferenceProfile(
        features=X_train,
        probs=probs,
        preds=preds,
        shap_by_class={c: shap_sub[preds_sub == c] for c in range(3)},
        benign_class_idx=0,
        num_classes=3,
        top_feature_indices=[0, 1, 2, 3, 4, 5],
    )
    monitor = DriftMonitorSuite(reference=ref, min_bucket_samples=5)
    clean_windows = []
    for w in range(10):
        X_w = _make_rows(rng, ["BENIGN"] * 50 + ["DDoS"] * 25 + ["DoS"] * 25)
        p, _, s, sp = engine.predict_and_explain(X_w, window_seed=w)
        clean_windows.append({"X": X_w, "probs": p, "shap_preds": sp, "shap": s})
    monitor.calibrate(clean_windows, percentile=95.0)

    # 5 benign-only windows, then 25 mixed windows (chronological test stream)
    labels = ["BENIGN"] * 500 + (["BENIGN"] * 20 + ["DDoS"] * 40 + ["DoS"] * 40) * 25
    test_df = pd.DataFrame(_make_rows(rng, labels), columns=FEATURES)
    test_df["target"] = labels
    return test_df, engine, monitor


def test_frozen_grid_plan_runs_deterministic_shifts_once():
    runs = grid.plan_runs(grid.ATTACKS, grid.SHIFT_TYPES, grid.SEEDS)
    # 3 attacks x (4 deterministic shifts x 1 seed + attack_mimicry x 3 seeds)
    assert len(runs) == 21
    assert {r["seed"] for r in runs if r["shift_type"] != "attack_mimicry"} == {grid.SEEDS[0]}


def test_run_grid_writes_evidence_files(tiny_setup, tmp_path):
    test_df, engine, monitor = tiny_setup
    out_dir = tmp_path / "grid"
    ctx = build_shift_context(test_df, FEATURES, ["DDoS"], seed=0, num_mimicry_features=2)
    results = grid.run_grid(
        test_df,
        FEATURES,
        engine,
        monitor,
        out_dir,
        attacks=["DDoS"],
        shift_types=["none", "attack_mimicry"],
        seeds=[1, 2],
        max_windows=20,
        shift_context=ctx,
        baseline_recalls={"DDoS": 1.0},
    )

    assert len(results) == 3 * 4  # 3 runs x 4 monitors
    assert set(results["monitor"]) == {"M1", "M2", "M3", "M4"}
    for name in ["results.csv", "windows.csv", "summary.csv", "summary.md", "config.json",
                 "stream_scores.csv", "stream_far.csv", "matched_far.csv", "lead_times.csv", "head_to_head.csv"]:
        assert (out_dir / name).exists()

    cfg = json.loads((out_dir / "config.json").read_text(encoding="utf-8"))
    assert cfg["num_runs"] == 3 and cfg["grid_version"] == grid.GRID_VERSION
    assert cfg["shift_spec"]["mimicry_features"]["DDoS"] == ctx.mimicry_features["DDoS"]

    alarmed = results.dropna(subset=["t_alarm"])
    assert (alarmed["detection_delay"] == alarmed["t_alarm"] - alarmed["shift_start_window"]).all()

    summary = pd.read_csv(out_dir / "summary.csv")
    assert len(summary) == 2 * 4  # 2 shift types x 4 monitors


def test_stream_scores_match_the_control_replay(tiny_setup, tmp_path):
    """FAR and alarm attribution rely on the stream scoring reproducing the unshifted replay exactly."""
    test_df, engine, monitor = tiny_setup
    out_dir = tmp_path / "grid"
    grid.run_grid(
        test_df, FEATURES, engine, monitor, out_dir, attacks=["DDoS"], shift_types=["none"],
        seeds=[1], max_windows=20, baseline_recalls={"DDoS": 1.0},
    )
    windows = pd.read_csv(out_dir / "windows.csv")
    stream = pd.read_csv(out_dir / "stream_scores.csv").set_index("window_id")
    cols = [f"m{i}_score" for i in range(1, 5)] + [f"m{i}_alert" for i in range(1, 5)]
    replay = windows.set_index("window_id")[cols]
    assert len(replay) > 0
    pd.testing.assert_frame_equal(replay, stream.loc[replay.index, cols], check_dtype=False)


def test_grid_refuses_to_run_without_a_control():
    with pytest.raises(ValueError, match="control"):
        grid.run_grid(pd.DataFrame(), [], None, None, None, shift_types=["attack_padding"])  # type: ignore[arg-type]
