from contextlib import asynccontextmanager
import json
import time
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sklearn.metrics import recall_score
from src.config import settings
from src.logger import get_logger, setup_logging
from src.service.model_engine import IDSEngine
from src.service.monitors import DriftMonitorSuite
from src.service.schemas import ExperimentRunRequest, ExperimentSummaryResponse
from src.service.shift_simulator import run_controlled_experiment

logger = get_logger(__name__)


class RuntimeStore:
    engine: Optional[IDSEngine] = None
    monitor: Optional[DriftMonitorSuite] = None
    test_df: Optional[pd.DataFrame] = None
    feature_cols: List[str] = []
    baseline_recalls: Dict[str, float] = {}
    history: Dict[int, dict] = {}


store = RuntimeStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Initializing EA-IDRS ML Service (log_level=%s)...", settings.LOG_LEVEL)

    model_path = settings.ARTIFACTS_DIR / "xgb_ids.joblib"
    ref_path = settings.ARTIFACTS_DIR / "reference_profile.joblib"
    thresh_path = settings.ARTIFACTS_DIR / "thresholds.json"
    metrics_path = settings.ARTIFACTS_DIR / "baseline_metrics.json"
    test_path = settings.SPLITS_DIR / "test_stream.parquet"
    meta_path = settings.SPLITS_DIR / "split_metadata.json"

    if model_path.exists() and ref_path.exists() and thresh_path.exists():
        store.engine = IDSEngine.load(model_path)
        store.monitor = DriftMonitorSuite.load(
            ref_path, thresh_path, min_bucket_samples=settings.MIN_BUCKET_SAMPLES
        )
        logger.info("Loaded XGBoost model and calibrated M1-M4 thresholds successfully.")
    else:
        logger.warning("Model or calibration artifacts missing in %s. Run train_and_calibrate.py first.", settings.ARTIFACTS_DIR)

    if metrics_path.exists():
        with open(metrics_path, encoding="utf-8") as f:
            rep = json.load(f)
        store.baseline_recalls = {
            k: v["recall"] for k, v in rep.items() if isinstance(v, dict) and "recall" in v
        }
        logger.debug("Loaded baseline per-class recalls: %s", store.baseline_recalls)

    if test_path.exists() and meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            store.feature_cols = json.load(f)["feature_cols"]
        store.test_df = pd.read_parquet(test_path)
        logger.info("Loaded test_stream.parquet (%d rows, %d windows).", len(store.test_df), len(store.test_df) // settings.WINDOW_SIZE)
    else:
        logger.warning("Test stream split not found at %s.", test_path)

    yield
    logger.info("Shutting down EA-IDRS ML Service.")


app = FastAPI(title="EA-IDRS ML Service", version="1.0.0", lifespan=lifespan)


class WindowPayload(BaseModel):
    window_id: int
    features: List[List[float]]


class UnlockRequest(BaseModel):
    window_id: int
    true_labels: Optional[List[str]] = None
    recall_drop_delta: float = 0.15


@app.get("/health")
def health():
    total_test_windows = (
        len(store.test_df) // settings.WINDOW_SIZE if store.test_df is not None else 0
    )
    return {
        "status": "ok",
        "artifacts_loaded": store.engine is not None and store.monitor is not None,
        "total_test_windows": total_test_windows,
        "window_size": settings.WINDOW_SIZE,
    }


def _score_matrix(
    window_id: int,
    X_win: np.ndarray,
    y_true_hidden: Optional[np.ndarray] = None,
    window_timestamp: Optional[str] = None,
) -> dict:
    if store.engine is None or store.monitor is None:
        logger.error("Evaluation requested for window %d before artifacts were loaded.", window_id)
        raise HTTPException(status_code=503, detail="Artifacts not loaded. Run train_and_calibrate.py first.")

    t0 = time.perf_counter()
    probs, preds, shap_sub, _ = store.engine.predict_and_explain(X_win, window_seed=window_id)
    res = store.monitor.evaluate_window(X_win, probs, preds, shap_sub)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    classes = store.engine.label_encoder.classes_
    named_shap = {
        str(classes[idx]): dist for idx, dist in res["per_class_shap_distance"].items()
    }

    store.history[window_id] = {
        "preds": preds,
        "y_true_hidden": y_true_hidden,
        "m1_alert": res["m1_alert"],
        "m2_alert": res["m2_alert"],
        "m3_alert": res["m3_alert"],
        "m4_alert": res["m4_alert"],
    }

    logger.info(
        "Window %d evaluated in %.1f ms | M3=%.3f (alert=%s) | M4=%.3f (alert=%s)",
        window_id,
        elapsed_ms,
        res["m3_score"],
        res["m3_alert"],
        res["m4_score"],
        res["m4_alert"],
    )
    logger.debug("Window %d per-class SHAP distances: %s", window_id, named_shap)

    return {
        "window_id": window_id,
        "timestamp": window_timestamp,
        "num_flows": int(len(X_win)),
        "latency_ms": round(elapsed_ms, 2),
        "thresholds": store.monitor.thresholds.__dict__,
        **res,
        "per_class_shap_distance": named_shap,
    }


@app.post("/evaluate-window")
def evaluate_window(payload: WindowPayload):
    X_win = np.asarray(payload.features, dtype=np.float32)
    return _score_matrix(payload.window_id, X_win)


@app.post("/replay-test-window/{window_id}")
def replay_test_window(window_id: int):
    if store.test_df is None:
        raise HTTPException(status_code=404, detail="test_stream.parquet not loaded.")
    start = window_id * settings.WINDOW_SIZE
    end = start + settings.WINDOW_SIZE
    if start < 0 or end > len(store.test_df):
        logger.warning("Requested out-of-range window_id=%d", window_id)
        raise HTTPException(status_code=400, detail="window_id out of range.")

    chunk = store.test_df.iloc[start:end]
    X_win = chunk[store.feature_cols].to_numpy(dtype=np.float32)
    y_hidden = chunk["target"].to_numpy()
    win_ts = str(chunk["timestamp"].iloc[0]) if "timestamp" in chunk.columns else None
    return _score_matrix(window_id, X_win, y_true_hidden=y_hidden, window_timestamp=win_ts)


@app.post("/unlock-labels")
def unlock_labels(req: UnlockRequest):
    if store.engine is None or req.window_id not in store.history:
        logger.warning("Unlock requested for unknown window_id=%d", req.window_id)
        raise HTTPException(status_code=404, detail="Window not evaluated yet.")

    entry = store.history[req.window_id]
    raw_labels = req.true_labels if req.true_labels is not None else entry["y_true_hidden"]
    if raw_labels is None:
        raise HTTPException(status_code=400, detail="No ground-truth labels available for this window.")

    y_true = store.engine.label_encoder.transform(raw_labels)
    preds = entry["preds"]
    classes = store.engine.label_encoder.classes_

    per_class_recall = {}
    degraded_classes = []

    for c_idx, c_name in enumerate(classes):
        c_str = str(c_name)
        mask = y_true == c_idx
        if np.sum(mask) >= 10:
            rec = float(recall_score(y_true == c_idx, preds == c_idx, zero_division=0))
            per_class_recall[c_str] = rec
            base_rec = store.baseline_recalls.get(c_str, 1.0)
            if c_str != "BENIGN" and (base_rec - rec) >= req.recall_drop_delta:
                degraded_classes.append(c_str)

    if degraded_classes:
        logger.warning("Window %d triggered t_fail! Degraded classes: %s", req.window_id, degraded_classes)
    else:
        logger.info("Window %d unlocked: no recall degradation detected.", req.window_id)

    return {
        "window_id": req.window_id,
        "per_class_recall": per_class_recall,
        "is_t_fail": len(degraded_classes) > 0,
        "degraded_classes": degraded_classes,
        "alerts": {
            "m1": entry["m1_alert"],
            "m2": entry["m2_alert"],
            "m3": entry["m3_alert"],
            "m4": entry["m4_alert"],
        },
    }


@app.get("/baseline-metrics")
def get_baseline_metrics():
    """Returns Experiment A per-class precision, recall, and F1 report."""
    metrics_path = settings.ARTIFACTS_DIR / "baseline_metrics.json"
    if not metrics_path.exists():
        raise HTTPException(status_code=404, detail="baseline_metrics.json not found.")
    with open(metrics_path, encoding="utf-8") as f:
        return json.load(f)


@app.post("/run-experiment", response_model=ExperimentSummaryResponse)
def run_experiment_endpoint(req: ExperimentRunRequest) -> ExperimentSummaryResponse:
    """Runs controlled shift replay (Experiments B/C/E/F) and returns M1-M4 comparison."""
    if store.engine is None or store.monitor is None or store.test_df is None:
        raise HTTPException(status_code=503, detail="Artifacts or test stream not loaded.")
    if req.target_attack not in store.engine.label_encoder.classes_:
        raise HTTPException(status_code=400, detail=f"Unknown target_attack: {req.target_attack}")

    result = run_controlled_experiment(
        test_df=store.test_df,
        feature_cols=store.feature_cols,
        engine=store.engine,
        monitor=store.monitor,
        target_attack=req.target_attack,
        shift_type=req.shift_type,
        shift_start_window=req.shift_start_window,
        max_windows=req.max_windows,
        recall_cutoff=req.recall_cutoff,
    )
    return ExperimentSummaryResponse(**result)
