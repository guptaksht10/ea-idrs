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


def build_shap_reference(
    engine: IDSEngine,
    X: np.ndarray,
    preds: np.ndarray,
    num_classes: int,
    per_class: int,
    rng: np.random.Generator,
) -> Dict[int, np.ndarray]:
    """Explains up to `per_class` flows of each predicted class; classes never predicted are left out."""
    shap_by_class: Dict[int, np.ndarray] = {}
    for c_idx in range(num_classes):
        idx = np.flatnonzero(preds == c_idx)
        if len(idx) == 0:
            continue
        if len(idx) > per_class:
            idx = np.sort(rng.choice(idx, size=per_class, replace=False))
        shap_by_class[c_idx] = engine.explain(X[idx], np.full(len(idx), c_idx))
    return shap_by_class


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

    # 2. Build Clean Reference Profile from the training split
    rng = np.random.default_rng(settings.RANDOM_SEED)
    # M1/M2 reference: random flows, so the feature and score reference keeps the natural class mix.
    ref_sample_size = min(settings.REFERENCE_SAMPLE_SIZE, len(X_train))
    ref_idx = rng.choice(len(X_train), size=ref_sample_size, replace=False)
    X_ref = X_train[ref_idx]
    ref_probs = engine.model.predict_proba(X_ref)
    ref_preds = np.argmax(ref_probs, axis=1)

    num_classes = len(classes)
    benign_idx = classes.index("BENIGN") if "BENIGN" in classes else 0
    top_k_indices = (
        np.argsort(engine.model.feature_importances_)[::-1][: settings.TOP_K_FEATURES]
        .astype(int)
        .tolist()
    )

    # M4 reference (R_c): stratified by predicted class, so rare classes get a usable bucket.
    logger.info(
        "Computing class-stratified reference SHAP profile (up to %d flows per predicted class)...",
        settings.SHAP_REFERENCE_PER_CLASS,
    )
    train_preds = engine.model.predict(X_train)
    shap_by_class = build_shap_reference(
        engine, X_train, train_preds, num_classes, settings.SHAP_REFERENCE_PER_CLASS, rng
    )
    for c_idx in range(num_classes):
        n_c = len(shap_by_class.get(c_idx, []))
        if n_c < settings.MIN_BUCKET_SAMPLES:
            logger.warning(
                "Reference SHAP bucket [%s] has %d samples (< %d); M4 ignores this class.",
                classes[c_idx],
                n_c,
                settings.MIN_BUCKET_SAMPLES,
            )
        else:
            logger.info("Reference SHAP bucket [%s]: %d samples", classes[c_idx], n_c)

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
        w_probs, _, w_shap, w_shap_preds = engine.predict_and_explain(X_w, window_seed=w_idx)
        clean_windows.append(
            {"X": X_w, "probs": w_probs, "shap_preds": w_shap_preds, "shap": w_shap}
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