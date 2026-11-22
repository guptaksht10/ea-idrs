import json
import pandas as pd
from src.config import settings
from src.logger import get_logger, setup_logging

logger = get_logger(__name__)


def build_chronological_splits(split_mode: str | None = None) -> None:
    mode = split_mode or settings.SPLIT_MODE
    clean_path = settings.PROCESSED_DIR / "cicids2017_clean.parquet"
    if not clean_path.exists():
        logger.error("Cleaned parquet not found at %s. Run clean_cicids.py first.", clean_path)
        raise FileNotFoundError(f"Missing {clean_path}")

    logger.info("Loading clean dataset from %s (mode=%s, label_mode=%s)", clean_path, mode, settings.LABEL_MODE)
    df = pd.read_parquet(clean_path, engine="pyarrow")

    target_col = "Macro_Label" if settings.LABEL_MODE == "macro" else "Label"
    df["target"] = df[target_col]

    counts = df["target"].value_counts()
    rare_classes = counts[counts < 50].index.tolist()
    if rare_classes:
        logger.warning("Dropping ultra-rare classes (<50 flows) from split: %s", rare_classes)
    valid_classes = counts[counts >= 50].index.tolist()
    df = df[df["target"].isin(valid_classes)].reset_index(drop=True)

    # Sort strictly chronologically on (day_order, row_order)
    df = df.sort_values(["day_order", "row_order"]).reset_index(drop=True)

    if mode == "strict_day":
        train_df = df[df["day_order"].isin([0, 1, 2])].reset_index(drop=True)
        val_df = df[df["day_order"] == 3].reset_index(drop=True)
        test_df = df[df["day_order"].isin([4, 5, 6, 7])].reset_index(drop=True)
    else:
        train_parts, val_parts, test_parts = [], [], []
        for cls_name, group in df.groupby("target", sort=False):
            n = len(group)
            t_end = int(n * 0.50)
            v_end = int(n * 0.65)
            logger.debug("Class %-14s | total=%7d -> train=%7d, val=%6d, test=%7d", cls_name, n, t_end, v_end - t_end, n - v_end)
            train_parts.append(group.iloc[:t_end])
            val_parts.append(group.iloc[t_end:v_end])
            test_parts.append(group.iloc[v_end:])

        train_df = pd.concat(train_parts).sort_values(["day_order", "row_order"]).reset_index(drop=True)
        val_df = pd.concat(val_parts).sort_values(["day_order", "row_order"]).reset_index(drop=True)
        test_df = pd.concat(test_parts).sort_values(["day_order", "row_order"]).reset_index(drop=True)

    settings.SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    train_df.to_parquet(settings.SPLITS_DIR / "train.parquet", index=False)
    val_df.to_parquet(settings.SPLITS_DIR / "val_clean.parquet", index=False)
    test_df.to_parquet(settings.SPLITS_DIR / "test_stream.parquet", index=False)

    meta_cols = {"Label", "Macro_Label", "day_order", "row_order", "timestamp", "target"}
    feature_cols = [c for c in df.columns if c not in meta_cols]

    metadata = {
        "split_mode": mode,
        "label_mode": settings.LABEL_MODE,
        "classes": sorted(valid_classes),
        "num_features": len(feature_cols),
        "feature_cols": feature_cols,
        "split_sizes": {
            "train": int(len(train_df)),
            "val_clean": int(len(val_df)),
            "test": int(len(test_df)),
        },
        "class_distribution_by_split": {
            "train": train_df["target"].value_counts().to_dict(),
            "val_clean": val_df["target"].value_counts().to_dict(),
            "test": test_df["target"].value_counts().to_dict(),
        },
    }
    with open(settings.SPLITS_DIR / "split_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Chronological splits complete: %s", metadata["split_sizes"])


if __name__ == "__main__":
    setup_logging()
    build_chronological_splits()