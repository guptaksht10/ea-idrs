from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
    RAW_DATA_DIR: Path = PROJECT_ROOT / "data" / "raw"
    PROCESSED_DIR: Path = PROJECT_ROOT / "data" / "processed"
    SPLITS_DIR: Path = PROCESSED_DIR / "splits"
    ARTIFACTS_DIR: Path = PROJECT_ROOT / "artifacts"
    NOTEBOOKS_DIR: Path = PROJECT_ROOT / "notebooks"

    # Logging ("DEBUG", "INFO", "WARNING", "ERROR")
    LOG_LEVEL: str = "INFO"

    # Dataset & Preprocessing
    LABEL_MODE: str = "macro"               # "macro" (8 classes) or "granular" (15 classes)
    SPLIT_MODE: str = "grouped_day_label"   # "grouped_day_label", "per_class_temporal" or "strict_day"
    SPLIT_TRAIN_FRAC: float = 0.50          # Earliest share of each group -> train
    SPLIT_VAL_FRAC: float = 0.15            # Next share -> clean validation (calibration); rest -> test
    CORR_THRESHOLD: float = 0.98            # Drop duplicate/collinear features with |r| > 0.98

    # Windowing & Calibration
    WINDOW_SIZE: int = 2000                 # ~2,000 flows per window
    SHAP_SAMPLE_SIZE: int = 512             # Fixed sample per window (Experiment D)
    REFERENCE_SAMPLE_SIZE: int = 20_000     # Random training flows for the M1/M2 reference (natural class mix)
    SHAP_REFERENCE_PER_CLASS: int = 1_000   # Training flows explained per predicted class for the M4 reference
    TOP_K_FEATURES: int = 15                # Top features tracked by M1 & M4
    MIN_BUCKET_SAMPLES: int = 15            # Min predicted samples per class bucket for SHAP distance
    CALIBRATION_PERCENTILE: float = 95.0    # 5% matched false-alarm budget

    # Reproducibility
    RANDOM_SEED: int = 42


settings = Settings()