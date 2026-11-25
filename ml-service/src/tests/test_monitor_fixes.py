"""Regression tests for the v2 monitor fixes (SHAP alignment, stratified reference, conformal scoring)."""

import json
import numpy as np
import pytest
from src.service.model_engine import IDSEngine
from src.service.monitors import (
    DriftMonitorSuite,
    ReferenceProfile,
    loo_surprisals,
    surprisal,
)
from src.service.train_and_calibrate import build_shap_reference

N_FEATURES = 6


def _data(rng: np.random.Generator, n_benign: int, n_ddos: int, n_bot: int):
    y = np.array(["BENIGN"] * n_benign + ["DDoS"] * n_ddos + ["Bot"] * n_bot)
    X = rng.normal(0, 1, size=(len(y), N_FEATURES)).astype(np.float32)
    X[y == "DDoS", 0] += 4.0
    X[y == "Bot", 1] += 4.0
    return X, y


@pytest.fixture(scope="module")
def engine():
    X, y = _data(np.random.default_rng(0), 400, 150, 20)  # Bot is rare, like in CIC-IDS2017
    return IDSEngine(shap_sample_size=64, random_state=42).fit(
        X, y, [f"f_{i}" for i in range(N_FEATURES)]
    )


def _suite(engine: IDSEngine, n_cal: int = 40) -> DriftMonitorSuite:
    rng = np.random.default_rng(1)
    X_ref, _ = _data(rng, 400, 150, 20)
    preds = engine.model.predict(X_ref)
    ref = ReferenceProfile(
        features=X_ref,
        probs=engine.model.predict_proba(X_ref),
        preds=preds,
        shap_by_class=build_shap_reference(engine, X_ref, preds, 3, 100, rng),
        benign_class_idx=1,
        num_classes=3,
        top_feature_indices=list(range(N_FEATURES)),
    )
    suite = DriftMonitorSuite(reference=ref, min_bucket_samples=5)
    windows = []
    for w in range(n_cal):
        X_w, _ = _data(rng, 200, 60, 10)
        p, _, s, sp = engine.predict_and_explain(X_w, window_seed=w)
        windows.append({"X": X_w, "probs": p, "shap_preds": sp, "shap": s})
    suite.calibrate(windows, percentile=95.0)
    return suite


def test_surprisal_is_bounded_conformal_score():
    cal = np.arange(1.0, 20.0)  # 19 calibration values
    assert surprisal(cal, 0.0) == pytest.approx(0.0)  # below everything -> p = 1
    assert surprisal(cal, 1e9) == pytest.approx(np.log(20))  # beyond everything -> p = 1/(n+1)
    assert surprisal(cal, 1e9) == surprisal(cal, 1e3)  # an extreme value cannot grow without bound


def test_loo_surprisals_match_brute_force():
    cal = np.array([0.3, 0.1, 0.3, 0.9, 0.5])
    expected = [surprisal(np.delete(cal, i), v) for i, v in enumerate(cal)]
    assert np.allclose(loo_surprisals(cal), expected)


def test_misaligned_shap_predictions_are_rejected(engine):
    suite = _suite(engine, n_cal=20)
    X_w, _ = _data(np.random.default_rng(5), 200, 60, 10)
    p, preds, s, _ = engine.predict_and_explain(X_w, window_seed=1)
    assert len(preds) != len(s)
    with pytest.raises(ValueError, match="preds_sub"):
        suite.evaluate_window(X_w, p, preds, s)  # whole-window preds: the old bug


def test_stratified_reference_gives_rare_classes_a_bucket(engine):
    rng = np.random.default_rng(2)
    X, _ = _data(rng, 2000, 300, 30)
    preds = engine.model.predict(X)
    ref = build_shap_reference(engine, X, preds, 3, per_class=100, rng=rng)
    for c in range(3):
        n_pred = int((preds == c).sum())
        assert len(ref[c]) == min(100, n_pred)
        assert ref[c].shape[1] == N_FEATURES
    bot = list(engine.label_encoder.classes_).index("Bot")
    assert len(ref[bot]) >= 15  # a random 512-flow sample would hold ~5 Bot flows


def test_clean_windows_stay_near_false_alarm_budget(engine):
    suite = _suite(engine, n_cal=60)
    rng = np.random.default_rng(9)
    alerts = []
    for w in range(60):
        X_w, _ = _data(rng, 200, 60, 10)
        p, _, s, sp = engine.predict_and_explain(X_w, window_seed=100 + w)
        res = suite.evaluate_window(X_w, p, sp, s)
        alerts.append([res[f"m{i}_alert"] for i in range(1, 5)])
    far = np.mean(alerts, axis=0)
    assert (far <= 0.15).all(), far  # 5% target, with slack for 60 windows


def test_save_load_roundtrip_and_old_format_rejected(engine, tmp_path):
    suite = _suite(engine, n_cal=20)
    ref_path, thr_path = tmp_path / "ref.joblib", tmp_path / "thr.json"
    suite.save(ref_path, thr_path)
    loaded = DriftMonitorSuite.load(ref_path, thr_path, min_bucket_samples=5)

    X_w, _ = _data(np.random.default_rng(3), 200, 60, 10)
    p, _, s, sp = engine.predict_and_explain(X_w, window_seed=3)
    assert loaded.evaluate_window(X_w, p, sp, s) == suite.evaluate_window(X_w, p, sp, s)

    old = {"m1_threshold": 1.0, "m2_threshold": 1.0, "m3_threshold": 1.0, "m4_threshold": 1.0,
           "m1_scale": 0.2, "m2_scale": 0.0003, "shap_scale": 0.09}
    thr_path.write_text(json.dumps(old), encoding="utf-8")
    with pytest.raises(ValueError, match="train_and_calibrate"):
        DriftMonitorSuite.load(ref_path, thr_path)
