"""Physically consistent, model-agnostic shifts for the controlled replay (grid v4 onwards).

Design rules (fixed 2026-11-25, before any v4 result was seen):
- Shifts act on named CICFlowMeter feature families, never on the model's feature importance,
  the monitors' tracked features or SHAP values, so no monitor is favoured by construction.
- Related features move together: slowing a flow down by k multiplies every duration and
  inter-arrival time by k and divides every rate by k; padding packets by d bytes moves every
  packet-size feature by d and updates byte totals and byte rates to match.
- Identifiers and protocol fields (port, flags, TCP window sizes, header lengths, packet counts)
  are never changed.
- Magnitudes below are fixed. Do not tune them to make a monitor look better; add a new
  version instead.
"""

from dataclasses import dataclass, field
from typing import Dict, List
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

# Microsecond durations and inter-arrival times.
TIME_FEATURES = [
    "Flow Duration",
    "Flow IAT Mean", "Flow IAT Std", "Flow IAT Max", "Flow IAT Min",
    "Fwd IAT Mean", "Fwd IAT Std", "Fwd IAT Min",
    "Bwd IAT Total", "Bwd IAT Mean", "Bwd IAT Std", "Bwd IAT Max", "Bwd IAT Min",
    "Active Mean", "Active Std", "Active Max", "Active Min", "Idle Std",
]
# Per-second rates (divide by the slow-down factor).
RATE_FEATURES = ["Flow Bytes/s", "Flow Packets/s", "Bwd Packets/s"]
# Per-packet sizes in bytes (shift by the padding). Std / variance do not change under padding.
SIZE_FEATURES = [
    "Fwd Packet Length Max", "Fwd Packet Length Min", "Fwd Packet Length Mean",
    "Bwd Packet Length Max", "Bwd Packet Length Min", "Bwd Packet Length Mean",
    "Min Packet Length", "Max Packet Length", "Packet Length Mean",
]
# Never shifted: identifiers, protocol/handshake fields and packet counts.
NEVER_SHIFT = [
    "Destination Port",
    "Fwd PSH Flags", "Fwd URG Flags", "FIN Flag Count", "RST Flag Count", "PSH Flag Count",
    "ACK Flag Count", "URG Flag Count",
    "Init_Win_bytes_forward", "Init_Win_bytes_backward",
    "Fwd Header Length", "Total Fwd Packets", "Down/Up Ratio",
]

# Fixed magnitudes at full severity (severity ramps 0 -> 1 over 8 windows in the simulator).
BENIGN_SLOWDOWN_MAX = 2.0   # benign traffic up to 2x slower (congestion, new usage)
LOW_RATE_MAX = 10.0         # attacker throttles up to 10x ("low and slow")
PADDING_MAX_BYTES = 256.0   # attacker pads every packet by up to 256 bytes (well under MTU)
MIMICRY_MAX_ALPHA = 0.9     # attack flows move up to 90% of the way to real benign flows
MIMICRY_NUM_FEATURES = 5    # on the attack's 5 most benign-distinguishable features
BENIGN_POOL_SIZE = 20_000

REALISTIC_SHIFTS = ("benign_slowdown", "attack_low_rate", "attack_padding", "attack_mimicry")
STOCHASTIC_REALISTIC_SHIFTS = {"attack_mimicry"}

# Severity ramps. "linear" (v1-v4): severity (i + 1) / R, capped at 1, so the first shifted window
# already carries 1/R of the full shift. "geometric" (v5): severity grows by a constant factor per
# window from GEOMETRIC_MIN_SEVERITY (1 byte of padding) to 1 over R windows. The model's recall
# responds to shift size over orders of magnitude (dose-response on the validation split), so a
# geometric ramp places windows below each attack's breaking point instead of jumping past it.
RAMPS = ("linear", "geometric")
GEOMETRIC_MIN_SEVERITY = 1.0 / PADDING_MAX_BYTES


def ramp_severity(windows_since_start: int, ramp_windows: int, ramp: str = "linear") -> float:
    """Shift severity in [0, 1] for the window `windows_since_start` windows after the shift start."""
    if ramp not in RAMPS:
        raise ValueError(f"Unknown ramp {ramp!r}; choose one of {RAMPS}.")
    if ramp_windows < 1:
        raise ValueError("ramp_windows must be >= 1.")
    if windows_since_start < 0:
        return 0.0
    if ramp == "linear":
        return min(1.0, (windows_since_start + 1) / ramp_windows)
    if ramp_windows == 1:
        return 1.0
    frac = min(windows_since_start, ramp_windows - 1) / (ramp_windows - 1)
    return float(GEOMETRIC_MIN_SEVERITY ** (1.0 - frac))


@dataclass
class ShiftContext:
    """Everything a realistic shift needs besides the window itself."""

    feature_index: Dict[str, int]
    mimicry_features: Dict[str, List[str]]
    benign_pool: np.ndarray = field(repr=False)

    def idx(self, names: List[str]) -> List[int]:
        return [self.feature_index[n] for n in names if n in self.feature_index]

    def describe(self) -> dict:
        return {
            "benign_slowdown_max": BENIGN_SLOWDOWN_MAX,
            "low_rate_max": LOW_RATE_MAX,
            "padding_max_bytes": PADDING_MAX_BYTES,
            "mimicry_max_alpha": MIMICRY_MAX_ALPHA,
            "mimicry_features": self.mimicry_features,
            "benign_pool_size": int(len(self.benign_pool)),
        }


def build_shift_context(
    ref_df: pd.DataFrame,
    feature_cols: List[str],
    target_attacks: List[str],
    seed: int,
    num_mimicry_features: int = MIMICRY_NUM_FEATURES,
    pool_size: int = BENIGN_POOL_SIZE,
) -> ShiftContext:
    """
    Builds the shift context from a labelled split that precedes the test stream (the clean
    validation split). Mimicry features are the target attack's features with the largest
    two-sample KS distance to benign traffic: model-free, and what an attacker who can observe
    normal traffic would change first.
    """
    rng = np.random.default_rng(seed)
    benign = ref_df.loc[ref_df["target"] == "BENIGN", feature_cols].to_numpy(np.float32)
    if len(benign) == 0:
        raise ValueError("Reference split has no BENIGN rows for the mimicry donor pool.")
    pool = benign[rng.choice(len(benign), size=min(pool_size, len(benign)), replace=False)]

    candidates = [c for c in feature_cols if c not in NEVER_SHIFT]
    mimicry: Dict[str, List[str]] = {}
    for attack in target_attacks:
        atk = ref_df.loc[ref_df["target"] == attack, candidates]
        if atk.empty:
            raise ValueError(f"Reference split has no rows of attack class {attack!r}.")
        dist = {c: float(ks_2samp(atk[c].to_numpy(), pool[:, feature_cols.index(c)]).statistic) for c in candidates}
        mimicry[attack] = sorted(dist, key=lambda c: (-dist[c], c))[:num_mimicry_features]

    return ShiftContext(
        feature_index={c: i for i, c in enumerate(feature_cols)},
        mimicry_features=mimicry,
        benign_pool=pool,
    )


def _time_dilate(X: np.ndarray, rows: np.ndarray, factor: float, ctx: ShiftContext) -> None:
    t_idx, r_idx = ctx.idx(TIME_FEATURES), ctx.idx(RATE_FEATURES)
    X[np.ix_(rows, t_idx)] *= factor
    X[np.ix_(rows, r_idx)] /= factor


def _pad(X: np.ndarray, rows: np.ndarray, pad_bytes: float, ctx: ShiftContext) -> None:
    fi = ctx.feature_index
    X[np.ix_(rows, ctx.idx(SIZE_FEATURES))] += pad_bytes
    if "Total Length of Fwd Packets" in fi and "Total Fwd Packets" in fi:
        X[rows, fi["Total Length of Fwd Packets"]] += pad_bytes * X[rows, fi["Total Fwd Packets"]]
    if "Flow Bytes/s" in fi and "Flow Packets/s" in fi:
        # bytes/s grows by pad x packets/s (every packet carries pad more bytes)
        X[rows, fi["Flow Bytes/s"]] += pad_bytes * X[rows, fi["Flow Packets/s"]]


def _mimic(
    X: np.ndarray, rows: np.ndarray, alpha: float, names: List[str], ctx: ShiftContext, rng: np.random.Generator
) -> None:
    cols = ctx.idx(names)
    donors = ctx.benign_pool[rng.integers(0, len(ctx.benign_pool), size=len(rows))][:, cols]
    X[np.ix_(rows, cols)] = (1.0 - alpha) * X[np.ix_(rows, cols)] + alpha * donors


def apply_realistic_shift(
    X_win: np.ndarray,
    y_true: np.ndarray,
    target_attack: str,
    shift_type: str,
    severity: float,
    ctx: ShiftContext,
    rng: np.random.Generator,
) -> np.ndarray:
    """Returns a shifted copy of X_win (X_win itself is never modified)."""
    if shift_type not in REALISTIC_SHIFTS:
        raise ValueError(f"Unknown realistic shift {shift_type!r}; choose one of {REALISTIC_SHIFTS}.")
    if severity <= 0.0:
        return X_win

    X = X_win.astype(np.float64, copy=True)
    attack_rows = np.flatnonzero(y_true == target_attack)
    benign_rows = np.flatnonzero(y_true == "BENIGN")

    if shift_type == "benign_slowdown" and len(benign_rows):
        _time_dilate(X, benign_rows, 1.0 + (BENIGN_SLOWDOWN_MAX - 1.0) * severity, ctx)
    elif shift_type == "attack_low_rate" and len(attack_rows):
        _time_dilate(X, attack_rows, 1.0 + (LOW_RATE_MAX - 1.0) * severity, ctx)
    elif shift_type == "attack_padding" and len(attack_rows):
        # Whole bytes only: a packet cannot carry a fraction of a byte.
        _pad(X, attack_rows, float(np.round(PADDING_MAX_BYTES * severity)), ctx)
    elif shift_type == "attack_mimicry" and len(attack_rows):
        _mimic(X, attack_rows, MIMICRY_MAX_ALPHA * severity, ctx.mimicry_features[target_attack], ctx, rng)

    return X.astype(X_win.dtype)
