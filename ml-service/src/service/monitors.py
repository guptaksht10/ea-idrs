from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Dict, List, Optional
import joblib
import numpy as np
from scipy.stats import ks_2samp, wasserstein_distance
from src.logger import get_logger

logger = get_logger(__name__)


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
    m1_threshold: float
    m2_threshold: float
    m3_threshold: float
    m4_threshold: float
    m1_scale: float
    m2_scale: float
    shap_scale: float


class DriftMonitorSuite:
    """
    Implements the 4-layer ablation drift monitor suite:
      M1: Feature-space drift (mean KS statistic across top-K features)
      M2: Output-score drift (Wasserstein distance on entropy + max-confidence + attack-prob)
      M3: Baseline composite monitor (normalized M1 + M2)
      M4: Explanation-aware monitor (M3 + class-conditional TreeSHAP Wasserstein shift)
    """

    def __init__(self, reference: ReferenceProfile, min_bucket_samples: int = 15) -> None:
        self.ref = reference
        self.min_bucket_samples = min_bucket_samples
        self.thresholds: Optional[CalibratedThresholds] = None
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
        self, preds: np.ndarray, shap_sub: np.ndarray
    ) -> tuple[float, Dict[int, float]]:
        """
        Buckets SHAP explanations by predicted class c and computes mean Wasserstein-1
        distance against clean reference bucket R_c across top-K features.
        """
        n_sub = len(shap_sub)
        preds_aligned = preds[:n_sub] if len(preds) != n_sub else preds

        per_class_dist: Dict[int, float] = {}
        weighted_sum = 0.0
        total_weight = 0

        for c_idx, ref_shap_c in self.ref.shap_by_class.items():
            mask = preds_aligned == c_idx
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

    def calibrate(
        self, clean_windows: List[dict], percentile: float = 95.0
    ) -> CalibratedThresholds:
        raw_m1, raw_m2, raw_shap = [], [], []
        for w in clean_windows:
            raw_m1.append(self.score_m1_feature_drift(w["X"]))
            raw_m2.append(self.score_m2_score_drift(w["probs"]))
            s_dist, _ = self.score_class_conditional_shap(w["preds"], w["shap"])
            raw_shap.append(s_dist)

        m1_scale = max(float(np.median(raw_m1)), 1e-6)
        m2_scale = max(float(np.median(raw_m2)), 1e-6)
        shap_scale = max(float(np.median(raw_shap)), 1e-6)

        norm_m1 = np.asarray(raw_m1) / m1_scale
        norm_m2 = np.asarray(raw_m2) / m2_scale
        norm_shap = np.asarray(raw_shap) / shap_scale

        m3_scores = 0.5 * (norm_m1 + norm_m2)
        m4_scores = (norm_m1 + norm_m2 + norm_shap) / 3.0

        self.thresholds = CalibratedThresholds(
            m1_threshold=float(np.percentile(norm_m1, percentile)),
            m2_threshold=float(np.percentile(norm_m2, percentile)),
            m3_threshold=float(np.percentile(m3_scores, percentile)),
            m4_threshold=float(np.percentile(m4_scores, percentile)),
            m1_scale=m1_scale,
            m2_scale=m2_scale,
            shap_scale=shap_scale,
        )
        return self.thresholds

    def evaluate_window(
        self,
        X_win: np.ndarray,
        probs: np.ndarray,
        preds: np.ndarray,
        shap_sub: np.ndarray,
    ) -> dict:
        if self.thresholds is None:
            raise RuntimeError("DriftMonitorSuite must be calibrated or loaded before evaluation.")

        t = self.thresholds
        m1_norm = self.score_m1_feature_drift(X_win) / t.m1_scale
        m2_norm = self.score_m2_score_drift(probs) / t.m2_scale
        shap_raw, per_class_shap = self.score_class_conditional_shap(preds, shap_sub)
        shap_norm = shap_raw / t.shap_scale

        m3_score = 0.5 * (m1_norm + m2_norm)
        m4_score = (m1_norm + m2_norm + shap_norm) / 3.0

        return {
            "m1_score": round(float(m1_norm), 4),
            "m2_score": round(float(m2_norm), 4),
            "m3_score": round(float(m3_score), 4),
            "m4_score": round(float(m4_score), 4),
            "m1_alert": bool(m1_norm > t.m1_threshold),
            "m2_alert": bool(m2_norm > t.m2_threshold),
            "m3_alert": bool(m3_score > t.m3_threshold),
            "m4_alert": bool(m4_score > t.m4_threshold),
            "per_class_shap_distance": per_class_shap,
        }

    def save(self, ref_path: Path, thresh_path: Path) -> None:
        if self.thresholds is None:
            raise RuntimeError("Cannot save uncalibrated DriftMonitorSuite.")
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.ref, ref_path)
        with open(thresh_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self.thresholds), f, indent=2)
        logger.info("Saved reference profile -> %s and thresholds -> %s", ref_path, thresh_path)

    @classmethod
    def load(
        cls, ref_path: Path, thresh_path: Path, min_bucket_samples: int = 15
    ) -> "DriftMonitorSuite":
        ref: ReferenceProfile = joblib.load(ref_path)
        with open(thresh_path, encoding="utf-8") as f:
            t_dict = json.load(f)
        suite = cls(reference=ref, min_bucket_samples=min_bucket_samples)
        suite.thresholds = CalibratedThresholds(**t_dict)
        return suite