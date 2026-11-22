# ml-service/src/preprocessing/clean_cicids.py
import json
from pathlib import Path
import numpy as np
import pandas as pd
from src.config import settings
from src.logger import get_logger, setup_logging

logger = get_logger(__name__)

CICIDS_FILES_ORDERED = [
    "Monday-WorkingHours.pcap_ISCX.csv",
    "Tuesday-WorkingHours.pcap_ISCX.csv",
    "Wednesday-workingHours.pcap_ISCX.csv",
    "Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv",
    "Thursday-WorkingHours-Afternoon-Infilteration.pcap_ISCX.csv",
    "Friday-WorkingHours-Morning.pcap_ISCX.csv",
    "Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv",
    "Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv",
]

SESSION_WINDOWS = {
    0: ("2017-07-03 09:00:00", 8 * 3600),
    1: ("2017-07-04 09:00:00", 8 * 3600),
    2: ("2017-07-05 09:00:00", 8 * 3600),
    3: ("2017-07-06 09:00:00", 4 * 3600),
    4: ("2017-07-06 13:00:00", 4 * 3600),
    5: ("2017-07-07 09:00:00", 4 * 3600),
    6: ("2017-07-07 13:00:00", 2.5 * 3600),
    7: ("2017-07-07 15:30:00", 1.5 * 3600),
}

MACRO_LABEL_MAP = {
    "BENIGN": "BENIGN",
    "DoS Hulk": "DoS",
    "DoS GoldenEye": "DoS",
    "DoS slowloris": "DoS",
    "DoS Slowhttptest": "DoS",
    "DDoS": "DDoS",
    "PortScan": "PortScan",
    "FTP-Patator": "BruteForce",
    "SSH-Patator": "BruteForce",
    "Bot": "Bot",
    "Web Attack - Brute Force": "WebAttack",
    "Web Attack - XSS": "WebAttack",
    "Web Attack - Sql Injection": "WebAttack",
    "Web Attack  Brute Force": "WebAttack",
    "Web Attack  XSS": "WebAttack",
    "Web Attack  Sql Injection": "WebAttack",
    "Infiltration": "Infiltration",
    "Heartbleed": "Heartbleed",
}


def attach_reconstructed_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Assigns monotonically increasing UTC timestamps per capture session."""
    timestamps = pd.Series(index=df.index, dtype="datetime64[ns]")
    for day_idx, (start_str, duration_sec) in SESSION_WINDOWS.items():
        mask = df["day_order"] == day_idx
        n_rows = int(mask.sum())
        if n_rows == 0:
            continue
        start_ts = pd.Timestamp(start_str)
        offsets = pd.to_timedelta(np.linspace(0, duration_sec, n_rows), unit="s")
        timestamps.loc[mask] = start_ts + offsets
    df["timestamp"] = timestamps
    return df


def run_cleaning() -> Path:
    logger.info("Starting CICIDS-2017 preprocessing pipeline...")
    dfs = []
    file_row_counts = {}

    for day_idx, filename in enumerate(CICIDS_FILES_ORDERED):
        file_path = settings.RAW_DATA_DIR / filename
        if not file_path.exists():
            logger.error("Missing expected raw CSV file: %s", file_path)
            raise FileNotFoundError(f"Missing expected raw CSV file: {file_path}")

        logger.info("Reading [%d/8]: %s", day_idx + 1, filename)
        df = pd.read_csv(file_path, encoding="latin1", low_memory=False)
        df.columns = df.columns.str.strip()

        if "Fwd Header Length.1" in df.columns:
            logger.debug("Dropping duplicate column 'Fwd Header Length.1' in %s", filename)
            df = df.drop(columns=["Fwd Header Length.1"])

        # Remove accidental mid-file header rows
        header_mask = df["Label"].astype(str).str.strip() == "Label"
        if header_mask.any():
            logger.warning("Removed %d repeated header rows in %s", int(header_mask.sum()), filename)
            df = df[~header_mask].copy()

        df["day_order"] = np.int8(day_idx)
        df["row_order"] = np.arange(len(df), dtype=np.int64)
        file_row_counts[filename] = int(len(df))
        dfs.append(df)

    combined = pd.concat(dfs, ignore_index=True)
    raw_total_rows = int(len(combined))
    logger.info("Combined raw rows across 8 files: %d", raw_total_rows)

    # Normalize label strings
    combined["Label"] = (
        combined["Label"]
        .astype(str)
        .str.strip()
        .str.replace("\x96", "-", regex=False)
    )
    combined["Macro_Label"] = combined["Label"].map(MACRO_LABEL_MAP).fillna("Other")

    unmapped = combined[combined["Macro_Label"] == "Other"]["Label"].unique().tolist()
    if unmapped:
        logger.warning("Unmapped granular labels assigned to 'Other': %s", unmapped)

    meta_cols = {"Label", "Macro_Label", "day_order", "row_order"}
    feature_cols = [c for c in combined.columns if c not in meta_cols]
    initial_feature_count = len(feature_cols)

    # Convert to numeric and sanitize Inf / NaN
    for col in feature_cols:
        combined[col] = pd.to_numeric(combined[col], errors="coerce")

    combined[feature_cols] = combined[feature_cols].replace([np.inf, -np.inf], np.nan)
    nan_rows_per_col = combined[feature_cols].isna().sum()
    cols_with_nans = nan_rows_per_col[nan_rows_per_col > 0].to_dict()
    logger.debug("NaN/Inf counts by column prior to drop: %s", cols_with_nans)

    combined = combined.dropna(subset=feature_cols).reset_index(drop=True)
    dropped_nan_rows = raw_total_rows - int(len(combined))
    logger.info("Dropped %d rows containing NaN/Inf (remaining: %d)", dropped_nan_rows, len(combined))

    # Drop zero-variance columns
    zero_var = [c for c in feature_cols if combined[c].nunique() <= 1]
    if zero_var:
        logger.warning("Dropping %d zero-variance features: %s", len(zero_var), zero_var)
        combined = combined.drop(columns=zero_var)
        feature_cols = [c for c in feature_cols if c not in zero_var]

    # Prune highly collinear features (|r| > CORR_THRESHOLD)
    sample_df = combined[feature_cols].sample(
        n=min(100_000, len(combined)), random_state=settings.RANDOM_SEED
    )
    corr_matrix = sample_df.corr().abs()
    upper_tri = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
    high_corr_cols = [
        col for col in upper_tri.columns if any(upper_tri[col] > settings.CORR_THRESHOLD)
    ]
    if high_corr_cols:
        logger.info(
            "Dropping %d collinear features (|r| > %.2f): %s",
            len(high_corr_cols),
            settings.CORR_THRESHOLD,
            high_corr_cols,
        )
        combined = combined.drop(columns=high_corr_cols)
        feature_cols = [c for c in feature_cols if c not in high_corr_cols]

    # Downcast numeric features to float32
    combined[feature_cols] = combined[feature_cols].astype(np.float32)

    # Attach reconstructed chronological timestamps
    combined = attach_reconstructed_timestamps(combined)

    out_path = settings.PROCESSED_DIR / "cicids2017_clean.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(out_path, engine="pyarrow", index=False)

    # Save audit summary for Notebook 01 visualizations
    audit = {
        "file_row_counts": file_row_counts,
        "raw_total_rows": raw_total_rows,
        "clean_total_rows": int(len(combined)),
        "dropped_nan_inf_rows": dropped_nan_rows,
        "initial_feature_count": initial_feature_count,
        "zero_variance_dropped": zero_var,
        "collinear_dropped": high_corr_cols,
        "final_feature_count": len(feature_cols),
        "granular_class_counts": combined["Label"].value_counts().to_dict(),
        "macro_class_counts": combined["Macro_Label"].value_counts().to_dict(),
    }
    audit_path = settings.PROCESSED_DIR / "preprocessing_audit.json"
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2)

    logger.info("Saved clean dataset %s -> %s", combined.shape, out_path)
    logger.info("Saved preprocessing audit -> %s", audit_path)
    return out_path


if __name__ == "__main__":
    setup_logging()
    run_cleaning()