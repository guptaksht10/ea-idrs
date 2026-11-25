import json
from typing import Dict, List
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report
from src.config import settings
from src.logger import get_logger, setup_logging
from src.service.model_engine import IDSEngine
from src.service.monitors import DriftMonitorSuite, ReferenceProfile

logger = get_logger(__name__)


def run_training_and_calibration() -> None:
    train_path = settings.SPLITS_DIR / "train.parquet"
    val_path = settings.SPLITS_DIR / "val_clean.parquet"
    meta_path = settings.SPLITS_DIR / "split_metadata.json"

    if not train_path.exists() or not val_path.exists() or not meta_path.exists():
        logger.error("Split files missing in %s. Run build_splits.py first.", settings.SPLITS_DIR)
        raise FileNotFoundError(f"Missing split parquet/metadata files in {settings.SPLITS_DIR}")

    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    feature_cols: List[str] = meta["feature_cols"]

    logger.info("Loading train.parquet and val_clean.parquet (%d features)...", len(feature_cols))
    train_df = pd.read_parquet(train_path, engine="pyarrow")
    val_df = pd.read_parquet(val_path, engine="pyarrow")

    X_train = train_df[feature_cols].to_numpy(dtype=np.float32)
    y_train = train_df["target"].to_numpy()
    X_val = val_df[feature_cols].to_numpy(dtype=np.float32)
    y_val = val_df["target"].to_numpy()

    # 1. Experiment A: Fit Baseline XGBoost + TreeSHAP Engine
    logger.info("Fitting XGBoost IDS Engine on %d flows...", len(X_train))
    engine = IDSEngine(
        shap_sample_size=settings.SHAP_SAMPLE_SIZE,
        random_state=settings.RANDOM_SEED,
    )
    engine.fit(X_train, y_train, feature_cols)

    # Evaluate Experiment A on Clean Validation Split
    val_probs = engine.model.predict_proba(X_val)
    val_preds = np.argmax(val_probs, axis=1)
    y_val_encoded = engine.label_encoder.transform(y_val)
    classes = [str(c) for c in engine.label_encoder.classes_]

    report = classification_report(
        y_val_encoded,
        val_preds,
        target_names=classes,
        output_dict=True,
        zero_division=0,
    )
    logger.info(
        "Experiment A Clean Val Macro-F1: %.4f | Weighted-F1: %.4f",
        report["macro avg"]["f1-score"],
        report["weighted avg"]["f1-score"],
    )

    # 2. Build Clean Reference Profile (R_c) from Stratified Training Sample
    ref_sample_size = min(20_000, len(X_train))
    rng = np.random.default_rng(settings.RANDOM_SEED)
    ref_idx = rng.choice(len(X_train), size=ref_sample_size, replace=False)
    X_ref = X_train[ref_idx]

    logger.info("Computing clean reference SHAP profile across %d flows...", ref_sample_size)
    ref_probs, ref_preds, ref_shap_sub, ref_preds_sub = engine.predict_and_explain(
        X_ref, window_seed=settings.RANDOM_SEED
    )

    num_classes = len(classes)
    benign_idx = classes.index("BENIGN") if "BENIGN" in classes else 0
    top_k_indices = (
        np.argsort(engine.model.feature_importances_)[::-1][: settings.TOP_K_FEATURES]
        .astype(int)
        .tolist()
    )

    shap_by_class: Dict[int, np.ndarray] = {}
    for c_idx in range(num_classes):
        mask = ref_preds_sub == c_idx
        if np.any(mask):
            shap_by_class[c_idx] = ref_shap_sub[mask]
            logger.debug("Reference SHAP bucket [%s]: %d samples", classes[c_idx], int(np.sum(mask)))
        else:
            logger.warning("Reference SHAP bucket [%s] has 0 predicted samples.", classes[c_idx])

    reference = ReferenceProfile(
        features=X_ref,
        probs=ref_probs,
        preds=ref_preds,
        shap_by_class=shap_by_class,
        benign_class_idx=benign_idx,
        num_classes=num_classes,
        top_feature_indices=top_k_indices,
    )

    # 3. Calibrate M1-M4 Thresholds at Matched 5% False-Alarm Rate (95th Percentile)
    monitor = DriftMonitorSuite(
        reference=reference,
        min_bucket_samples=settings.MIN_BUCKET_SAMPLES,
    )

    step = settings.WINDOW_SIZE
    clean_windows = []
    for w_idx, start in enumerate(range(0, len(X_val) - step + 1, step)):
        X_w = X_val[start : start + step]
        w_probs, w_preds, w_shap, _ = engine.predict_and_explain(X_w, window_seed=w_idx)
        clean_windows.append(
            {"X": X_w, "probs": w_probs, "preds": w_preds, "shap": w_shap}
        )

    logger.info(
        "Calibrating M1-M4 thresholds across %d clean validation windows (percentile=%.1f)...",
        len(clean_windows),
        settings.CALIBRATION_PERCENTILE,
    )
    thresholds = monitor.calibrate(clean_windows, percentile=settings.CALIBRATION_PERCENTILE)

    # 4. Save Artifacts
    settings.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    engine.save(settings.ARTIFACTS_DIR / "xgb_ids.joblib")
    monitor.save(
        settings.ARTIFACTS_DIR / "reference_profile.joblib",
        settings.ARTIFACTS_DIR / "thresholds.json",
    )
    with open(settings.ARTIFACTS_DIR / "baseline_metrics.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("Saved all model & calibration artifacts to %s", settings.ARTIFACTS_DIR)
    logger.info("Frozen Thresholds (5%% FAR): %s", thresholds.__dict__)


if __name__ == "__main__":
    setup_logging()
    run_training_and_calibration()