"""Dose-response of the detector: target-attack recall as shift severity grows (model only, no monitors).

This is the evidence for the v5 severity ramp. It runs on the clean validation split, never on the
test stream, and it never looks at monitor scores, so the ramp it motivates favours no monitor.

Usage (from ml-service/):
    python -m src.service.dose_response
"""

from datetime import datetime, timezone
import json
from typing import List, Sequence
import numpy as np
import pandas as pd
from src.config import settings
from src.logger import get_logger, setup_logging
from src.service.model_engine import IDSEngine
from src.service.shifts import (
    BENIGN_SLOWDOWN_MAX,
    LOW_RATE_MAX,
    MIMICRY_MAX_ALPHA,
    PADDING_MAX_BYTES,
    ShiftContext,
    apply_realistic_shift,
    build_shift_context,
)

logger = get_logger(__name__)

ATTACK_SHIFTS = ["attack_low_rate", "attack_padding", "attack_mimicry"]
# Doubling steps from 1 byte of padding up to the full shift, plus 0 for the baseline.
SEVERITIES: List[float] = [0.0] + [2.0**k / PADDING_MAX_BYTES for k in range(0, 9)]


def magnitude(shift_type: str, severity: float) -> str:
    if shift_type == "attack_padding":
        return f"{int(np.round(PADDING_MAX_BYTES * severity))} B"
    if shift_type == "attack_low_rate":
        return f"x{1.0 + (LOW_RATE_MAX - 1.0) * severity:.2f}"
    if shift_type == "benign_slowdown":
        return f"x{1.0 + (BENIGN_SLOWDOWN_MAX - 1.0) * severity:.2f}"
    return f"alpha {MIMICRY_MAX_ALPHA * severity:.4f}"


def dose_response(
    df: pd.DataFrame,
    feature_cols: List[str],
    engine: IDSEngine,
    ctx: ShiftContext,
    attacks: Sequence[str],
    shift_types: Sequence[str] = ATTACK_SHIFTS,
    severities: Sequence[float] = SEVERITIES,
    seed: int = 42,
    max_attack_rows: int = 20_000,
) -> pd.DataFrame:
    """Recall of each attack on its own flows after the shift is applied at each severity."""
    rows = []
    for attack in attacks:
        atk = df[df["target"] == attack]
        atk = atk.sample(n=min(max_attack_rows, len(atk)), random_state=seed)
        X = atk[feature_cols].to_numpy(np.float32)
        y = atk["target"].to_numpy()
        for shift in shift_types:
            for sev in severities:
                Xs = apply_realistic_shift(X, y, attack, shift, sev, ctx, np.random.default_rng(seed))
                pred = engine.label_encoder.inverse_transform(engine.model.predict(Xs))
                rows.append(
                    {
                        "attack": attack,
                        "shift_type": shift,
                        "severity": round(sev, 6),
                        "magnitude": magnitude(shift, sev),
                        "recall": round(float((pred == attack).mean()), 4),
                        "flows": len(atk),
                    }
                )
    return pd.DataFrame(rows)


def main() -> None:
    with open(settings.SPLITS_DIR / "split_metadata.json", encoding="utf-8") as f:
        feature_cols: List[str] = json.load(f)["feature_cols"]
    engine = IDSEngine.load(settings.ARTIFACTS_DIR / "xgb_ids.joblib")
    val_df = pd.read_parquet(settings.SPLITS_DIR / "val_clean.parquet", columns=feature_cols + ["target"])
    attacks = ["DDoS", "DoS", "PortScan"]
    ctx = build_shift_context(val_df, feature_cols, attacks, seed=settings.RANDOM_SEED)
    result = dose_response(val_df, feature_cols, engine, ctx, attacks, seed=settings.RANDOM_SEED)

    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_dose_response"
    out_dir = settings.ARTIFACTS_DIR / "experiments" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_dir / "dose_response.csv", index=False)
    logger.info("Dose-response written to %s", out_dir)
    for (attack, shift), grp in result.groupby(["attack", "shift_type"], sort=False):
        print(f"{attack:9s} {shift:16s} " + "  ".join(f"{m}={r:.3f}" for m, r in zip(grp["magnitude"], grp["recall"])))


if __name__ == "__main__":
    setup_logging()
    main()
