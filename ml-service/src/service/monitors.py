from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Dict, List, Optional
import joblib
import numpy as np
from scipy.stats import ks_2samp, wasserstein_distance
from src.logger import get_logger

logger = get_logger(__name__)

SIGNALS = ("m1", "m2", "shap")


@dataclass
class ReferenceProfile:
    features: np.ndarray
    probs: np.ndarray
    preds: np.ndarray
    shap_by_class: Dict[int, np.ndarray]
    benign_class_idx: int
    num_classes: int
    top_feature_indices: List[int]


@dataclass
class CalibratedThresholds:
    """Alarm thresholds in surprisal units (-ln conformal p-value), one per monitor."""

    m1_threshold: float
    m2_threshold: float
    m3_threshold: float
    m4_threshold: float


@dataclass
class CalibrationScores:
    """Raw signal values of the clean calibration windows (the conformal reference)."""

    m1: np.ndarray
    m2: np.ndarray
    shap: np.ndarray

    def get(self, name: str) -> np.ndarray:
        return getattr(self, name)


def surprisal(cal: np.ndarray, value: float) -> float:
    """
    -ln of the conformal p-value of `value` against the calibration values `cal`:
    p = (1 + #{cal >= value}) / (n + 1). 0 = completely ordinary, ln(n + 1) = beyond every
    calibration window. Bounded, so one extreme signal cannot swamp a composite score.
    """
    n_ge = int(np.sum(cal >= value))
    return float(-np.log((1 + n_ge) / (len(cal) + 1)))


def loo_surprisals(cal: np.ndarray) -> np.ndarray:
    """Leave-one-out surprisal of each calibration value against the other n - 1 values."""
    n = len(cal)
    sorted_cal = np.sort(cal)
    # #{j: cal_j >= cal_i} includes i itself, which is exactly the "+1" of the conformal p-value.
    n_ge = n - np.searchsorted(sorted_cal, cal, side="left")
    return -np.log(n_ge / n)


class DriftMonitorSuite:
    """
    Implements the 4-layer ablation drift monitor suite:
      M1: Feature-space drift (mean KS statistic across top-K features)
      M2: Output-score drift (Wasserstein distance on entropy + max-confidence)
      M3: Baseline composite monitor (M1 + M2)
      M4: Explanation-aware monitor (M1 + M2 + class-conditional TreeSHAP Wasserstein shift)

    Each raw signal is turned into a surprisal (-ln conformal p-value) against the clean
    calibration windows, so all signals share one bounded scale. M3 and M4 are the mean
    surprisal of their signals. Every threshold is the 95th percentile of that monitor's
    leave-one-out calibration scores, which matches the false-alarm budget across monitors.
    """

    def __init__(self, reference: ReferenceProfile, min_bucket_samples: int = 15) -> None:
        self.ref = reference
        self.min_bucket_samples = min_bucket_samples
        self.thresholds: Optional[CalibratedThresholds] = None
        self.calibration: Optional[CalibrationScores] = None
        self._ref_score_sigs = self._compute_score_signals(reference.probs)

    @staticmethod
    def _compute_score_signals(probs: np.ndarray) -> np.ndarray:
        eps = 1e-12
        clipped = np.clip(probs, eps, 1.0)
        entropy = -np.sum(clipped * np.log(clipped), axis=1)
        max_conf = np.max(clipped, axis=1)
        return np.column_stack([entropy, max_conf])

    def score_m1_feature_drift(self, X_win: np.ndarray) -> float:
        ks_vals = [
            float(ks_2samp(self.ref.features[:, idx], X_win[:, idx]).statistic)
            for idx in self.ref.top_feature_indices
        ]
        return float(np.mean(ks_vals)) if ks_vals else 0.0

    def score_m2_score_drift(self, probs: np.ndarray) -> float:
        win_sigs = self._compute_score_signals(probs)
        d_ent = float(wasserstein_distance(self._ref_score_sigs[:, 0], win_sigs[:, 0]))
        d_conf = float(wasserstein_distance(self._ref_score_sigs[:, 1], win_sigs[:, 1]))
        return 0.5 * (d_ent + d_conf)

    def score_class_conditional_shap(
        self, shap_preds: np.ndarray, shap_sub: np.ndarray
    ) -> tuple[float, Dict[int, float]]:
        """
        Buckets SHAP explanations by predicted class c and computes mean Wasserstein-1
        distance against clean reference bucket R_c across top-K features.

        shap_preds[i] must be the predicted class of the flow explained in shap_sub[i]
        (the `preds_sub` returned by IDSEngine.predict_and_explain).
        """
        if len(shap_preds) != len(shap_sub):
            raise ValueError(
                f"shap_preds has {len(shap_preds)} rows but shap_sub has {len(shap_sub)}; "
                "pass the predictions of the explained flows (preds_sub), not the whole window."
            )

        per_class_dist: Dict[int, float] = {}
        weighted_sum = 0.0
        total_weight = 0

        for c_idx, ref_shap_c in self.ref.shap_by_class.items():
            mask = shap_preds == c_idx
            count = int(np.sum(mask))
            if count < self.min_bucket_samples or len(ref_shap_c) < self.min_bucket_samples:
                continue

            win_shap_c = shap_sub[mask]
            feat_dists = [
                float(wasserstein_distance(ref_shap_c[:, f_idx], win_shap_c[:, f_idx]))
                for f_idx in self.ref.top_feature_indices
            ]
            c_dist = float(np.mean(feat_dists))
            per_class_dist[c_idx] = round(c_dist, 6)
            weighted_sum += c_dist * count
            total_weight += count

        agg_shap_dist = float(weighted_sum / total_weight) if total_weight > 0 else 0.0
        return agg_shap_dist, per_class_dist

    def _raw_signals(
        self, X_win: np.ndarray, probs: np.ndarray, shap_preds: np.ndarray, shap_sub: np.ndarray
    ) -> tuple[Dict[str, float], Dict[int, float]]:
        shap_raw, per_class = self.score_class_conditional_shap(shap_preds, shap_sub)
        raw = {
            "m1": self.score_m1_feature_drift(X_win),
            "m2": self.score_m2_score_drift(probs),
            "shap": shap_raw,
        }
        return raw, per_class

    @staticmethod
    def _combine(u: Dict[str, float] | Dict[str, np.ndarray]) -> dict:
        return {
            "m1": u["m1"],
            "m2": u["m2"],
            "m3": (u["m1"] + u["m2"]) / 2.0,
            "m4": (u["m1"] + u["m2"] + u["shap"]) / 3.0,
        }

    def calibrate(
        self, clean_windows: List[dict], percentile: float = 95.0
    ) -> CalibratedThresholds:
        """
        clean_windows: dicts with "X", "probs", "shap" and "shap_preds"
        (the predictions of the explained flows, i.e. preds_sub).
        """
        if len(clean_windows) < 20:
            logger.warning(
                "Only %d calibration windows; the %.0fth-percentile thresholds will be coarse.",
                len(clean_windows),
                percentile,
            )
        raws = [
            self._raw_signals(w["X"], w["probs"], w["shap_preds"], w["shap"])[0]
            for w in clean_windows
        ]
        self.calibration = CalibrationScores(
            **{s: np.asarray([r[s] for r in raws], dtype=np.float64) for s in SIGNALS}
        )
        loo = {s: loo_surprisals(self.calibration.get(s)) for s in SIGNALS}
        scores = self._combine(loo)

        self.thresholds = CalibratedThresholds(
            **{f"{m}_threshold": float(np.percentile(scores[m], percentile)) for m in scores}
        )
        return self.thresholds

    def evaluate_window(
        self,
        X_win: np.ndarray,
        probs: np.ndarray,
        shap_preds: np.ndarray,
        shap_sub: np.ndarray,
    ) -> dict:
        """shap_preds must be preds_sub from IDSEngine.predict_and_explain (aligned with shap_sub)."""
        if self.thresholds is None or self.calibration is None:
            raise RuntimeError("DriftMonitorSuite must be calibrated or loaded before evaluation.")

        raw, per_class_shap = self._raw_signals(X_win, probs, shap_preds, shap_sub)
        u = {s: surprisal(self.calibration.get(s), raw[s]) for s in SIGNALS}
        scores = self._combine(u)
        t = asdict(self.thresholds)

        result: dict = {}
        for m, score in scores.items():
            result[f"{m}_score"] = round(float(score), 4)
            result[f"{m}_alert"] = bool(score > t[f"{m}_threshold"])
        result.update(
            {
                "raw_m1": round(raw["m1"], 6),
                "raw_m2": round(raw["m2"], 6),
                "raw_shap": round(raw["shap"], 6),
                "per_class_shap_distance": per_class_shap,
            }
        )
        return result

    def save(self, ref_path: Path, thresh_path: Path) -> None:
        if self.thresholds is None or self.calibration is None:
            raise RuntimeError("Cannot save uncalibrated DriftMonitorSuite.")
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.ref, ref_path)
        payload = {
            **asdict(self.thresholds),
            "score_units": "surprisal = -ln(conformal p-value vs clean calibration windows)",
            "calibration_scores": {s: self.calibration.get(s).tolist() for s in SIGNALS},
        }
        with open(thresh_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        logger.info("Saved reference profile -> %s and thresholds -> %s", ref_path, thresh_path)

    @classmethod
    def load(
        cls, ref_path: Path, thresh_path: Path, min_bucket_samples: int = 15
    ) -> "DriftMonitorSuite":
        ref: ReferenceProfile = joblib.load(ref_path)
        with open(thresh_path, encoding="utf-8") as f:
            payload = json.load(f)
        if "calibration_scores" not in payload:
            raise ValueError(
                f"{thresh_path} was written by the old median-scaled monitors; "
                "re-run `python -m src.service.train_and_calibrate`."
            )
        suite = cls(reference=ref, min_bucket_samples=min_bucket_samples)
        suite.calibration = CalibrationScores(
            **{s: np.asarray(payload["calibration_scores"][s], dtype=np.float64) for s in SIGNALS}
        )
        suite.thresholds = CalibratedThresholds(
            **{f"{m}_threshold": float(payload[f"{m}_threshold"]) for m in ("m1", "m2", "m3", "m4")}
        )
        return suite
