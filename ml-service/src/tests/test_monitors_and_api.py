import numpy as np
from fastapi.testclient import TestClient
from src.service.main import app
from src.service.model_engine import IDSEngine
from src.service.monitors import DriftMonitorSuite, ReferenceProfile


def test_monitor_calibration_and_shap_shift_detection():
    rng = np.random.default_rng(42)
    n_features = 10
    X_train = rng.normal(0, 1, size=(300, n_features)).astype(np.float32)
    y_train = np.array(["BENIGN"] * 150 + ["DDoS"] * 150)
    X_train[150:, 0] += 3.0  # Separate DDoS on feature 0

    engine = IDSEngine(shap_sample_size=64, random_state=42)
    engine.fit(X_train, y_train, [f"f_{i}" for i in range(n_features)])

    probs, preds, shap_sub, preds_sub = engine.predict_and_explain(X_train, window_seed=1)
    ref = ReferenceProfile(
        features=X_train,
        probs=probs,
        preds=preds,
        shap_by_class={c: shap_sub[preds_sub == c] for c in [0, 1]},
        benign_class_idx=0,
        num_classes=2,
        top_feature_indices=[0, 1, 2],
    )
    suite = DriftMonitorSuite(reference=ref, min_bucket_samples=10)

    # Identical clean windows: every leave-one-out surprisal is 0, so all thresholds are 0.
    clean_windows = [
        {"X": X_train, "probs": probs, "shap_preds": preds_sub, "shap": shap_sub}
        for _ in range(10)
    ]
    thresholds = suite.calibrate(clean_windows, percentile=95.0)
    assert thresholds.m4_threshold >= thresholds.m3_threshold

    # Simulate drifted SHAP attributions for predicted DDoS bucket
    drifted_shap = shap_sub.copy()
    drifted_shap[preds_sub == 1, 0] += 5.0
    eval_res = suite.evaluate_window(X_train, probs, preds_sub, drifted_shap)
    assert eval_res["m4_alert"] is True
    assert eval_res["m3_alert"] is False  # features and scores did not change, only explanations
    assert eval_res["m4_score"] > eval_res["m3_score"]


def test_health_endpoint():
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"

def test_all_api_routes_registered():
    """Guards against main.py losing endpoints (e.g. a file overwrite during a merge)."""
    paths = {route.path for route in app.routes}
    expected = {
        "/health",
        "/evaluate-window",
        "/replay-test-window/{window_id}",
        "/unlock-labels",
        "/baseline-metrics",
        "/run-experiment",
    }
    assert expected <= paths
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200


def test_run_experiment_uses_baseline_drop_rule_by_default():
    """The demo endpoint must flag degradation with the same rule as grid v5 and /unlock-labels."""
    from src.service.main import degradation_cutoff
    from src.service.schemas import ExperimentRunRequest

    baselines = {"DDoS": 0.9997, "PortScan": 1.0}
    default = ExperimentRunRequest(target_attack="DDoS")
    assert default.recall_drop == 0.15
    assert abs(degradation_cutoff(default, baselines) - 0.8497) < 1e-9
    # A drop of exactly 0.15 counts (simulator uses recall < cutoff).
    assert 1.0 - 0.15 < degradation_cutoff(ExperimentRunRequest(target_attack="PortScan"), baselines)
    # Legacy absolute rule when recall_drop is null.
    legacy = ExperimentRunRequest(target_attack="DDoS", recall_drop=None, recall_cutoff=0.8)
    assert degradation_cutoff(legacy, baselines) == 0.8
