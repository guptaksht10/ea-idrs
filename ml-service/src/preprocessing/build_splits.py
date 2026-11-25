import json
from typing import Dict, List, Tuple
import pandas as pd
from src.config import settings
from src.logger import get_logger, setup_logging

logger = get_logger(__name__)

# Columns whose groups are each cut chronologically into train / val / test.
#   grouped_day_label: every (capture day, original label) group, e.g. (Friday, BENIGN), (Wednesday, DoS Hulk).
#     Every split then holds benign traffic from every day and every attack variant, so validation
#     (calibration) traffic looks like test traffic. Recommended; see README "Split".
#   per_class_temporal: every model class across the whole week (original design, used by grid v1/v2).
#     Benign ends up as Mon-Wed train / Wed-Thu val / Thu-Fri test.
GROUP_KEYS: Dict[str, List[str]] = {
    "grouped_day_label": ["day_order", "Label"],
    "per_class_temporal": ["target"],
}
SPLIT_MODES = (*GROUP_KEYS, "strict_day")
TIME_ORDER = ["day_order", "row_order"]  # row order within a day is the capture order


def split_frame(
    df: pd.DataFrame, mode: str, train_frac: float, val_frac: float
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Splits chronologically. Within each group the earliest `train_frac` of rows train, the next
    `val_frac` validate and the rest test, so no row is ever trained on after a row it is tested on
    within the same group. Each split comes back sorted in capture order.
    """
    if mode not in SPLIT_MODES:
        raise ValueError(f"Unknown split mode {mode!r}; choose one of {SPLIT_MODES}.")
    if not (0.0 < train_frac and 0.0 < val_frac and train_frac + val_frac < 1.0):
        raise ValueError("Need 0 < train_frac, 0 < val_frac and train_frac + val_frac < 1.")

    df = df.sort_values(TIME_ORDER).reset_index(drop=True)
    if mode == "strict_day":
        return (
            df[df["day_order"].isin([0, 1, 2])].reset_index(drop=True),
            df[df["day_order"] == 3].reset_index(drop=True),
            df[df["day_order"].isin([4, 5, 6, 7])].reset_index(drop=True),
        )

    train_parts, val_parts, test_parts = [], [], []
    for key, group in df.groupby(GROUP_KEYS[mode], sort=False):
        n = len(group)
        t_end = int(n * train_frac)
        v_end = int(n * (train_frac + val_frac))
        logger.debug("Group %-40s | total=%7d -> train=%7d, val=%6d, test=%7d", key, n, t_end, v_end - t_end, n - v_end)
        train_parts.append(group.iloc[:t_end])
        val_parts.append(group.iloc[t_end:v_end])
        test_parts.append(group.iloc[v_end:])

    def _ordered(parts: List[pd.DataFrame]) -> pd.DataFrame:
        return pd.concat(parts).sort_values(TIME_ORDER).reset_index(drop=True)

    return _ordered(train_parts), _ordered(val_parts), _ordered(test_parts)


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

    train_df, val_df, test_df = split_frame(
        df, mode, settings.SPLIT_TRAIN_FRAC, settings.SPLIT_VAL_FRAC
    )

    settings.SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    train_df.to_parquet(settings.SPLITS_DIR / "train.parquet", index=False)
    val_df.to_parquet(settings.SPLITS_DIR / "val_clean.parquet", index=False)
    test_df.to_parquet(settings.SPLITS_DIR / "test_stream.parquet", index=False)

    meta_cols = {"Label", "Macro_Label", "day_order", "row_order", "timestamp", "target"}
    feature_cols = [c for c in df.columns if c not in meta_cols]
    splits = {"train": train_df, "val_clean": val_df, "test": test_df}

    metadata = {
        "split_mode": mode,
        "group_keys": GROUP_KEYS.get(mode),
        "train_frac": settings.SPLIT_TRAIN_FRAC,
        "val_frac": settings.SPLIT_VAL_FRAC,
        "label_mode": settings.LABEL_MODE,
        "classes": sorted(valid_classes),
        "num_features": len(feature_cols),
        "feature_cols": feature_cols,
        "split_sizes": {name: int(len(part)) for name, part in splits.items()},
        "class_distribution_by_split": {
            name: part["target"].value_counts().to_dict() for name, part in splits.items()
        },
        "benign_rows_by_day_by_split": {
            name: {
                str(day): int(n)
                for day, n in part.loc[part["target"] == "BENIGN", "day_order"].value_counts().sort_index().items()
            }
            for name, part in splits.items()
        },
    }
    with open(settings.SPLITS_DIR / "split_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Chronological splits complete: %s", metadata["split_sizes"])


if __name__ == "__main__":
    setup_logging()
    build_chronological_splits()
