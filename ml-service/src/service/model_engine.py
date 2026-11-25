from pathlib import Path
from typing import List, Optional, Tuple
import joblib
import numpy as np
import shap
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier
from src.logger import get_logger

logger = get_logger(__name__)


class IDSEngine:
    """XGBoost multi-class intrusion detector paired with TreeSHAP attribution."""

    def __init__(self, shap_sample_size: int = 512, random_state: int = 42) -> None:
        self.shap_sample_size = shap_sample_size
        self.random_state = random_state
        self.label_encoder = LabelEncoder()
        self.feature_names: List[str] = []
        self.model = XGBClassifier(
            n_estimators=250,
            max_depth=6,
            learning_rate=0.08,
            subsample=0.85,
            colsample_bytree=0.85,
            objective="multi:softprob",
            eval_metric="mlogloss",
            tree_method="hist",
            n_jobs=-1,
            random_state=random_state,
        )
        self.explainer: Optional[shap.TreeExplainer] = None

    def fit(self, X_train: np.ndarray, y_train: np.ndarray, feature_names: List[str]) -> "IDSEngine":
        self.feature_names = list(feature_names)
        y_enc = self.label_encoder.fit_transform(y_train)
        sample_weights = compute_sample_weight(class_weight="balanced", y=y_enc)
        # multi:softprob needs num_class; XGBoost only infers it for >2 classes.
        self.model.set_params(num_class=len(self.label_encoder.classes_))

        logger.info(
            "Training XGBClassifier | samples=%d | features=%d | classes=%d",
            len(X_train),
            len(self.feature_names),
            len(self.label_encoder.classes_),
        )
        self.model.fit(X_train, y_enc, sample_weight=sample_weights)
        self.explainer = shap.TreeExplainer(self.model)
        logger.info("XGBClassifier and TreeExplainer initialized successfully.")
        return self

    def predict_and_explain(
        self, X_win: np.ndarray, window_seed: int = 42
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Returns:
          probs: (N, C) predicted class probabilities
          preds: (N,) predicted class indices
          shap_sub: (M, F) SHAP attributions for each flow's predicted class on M <= shap_sample_size flows
          preds_sub: (M,) predicted class indices for the M subsampled flows.
            Row i of shap_sub belongs to preds_sub[i]; pass preds_sub (not preds) to the monitors.
        """
        probs = self.model.predict_proba(X_win)
        preds = np.argmax(probs, axis=1)

        n_rows = len(X_win)
        if n_rows > self.shap_sample_size:
            rng = np.random.default_rng(self.random_state + window_seed)
            sub_idx = np.sort(rng.choice(n_rows, size=self.shap_sample_size, replace=False))
        else:
            sub_idx = np.arange(n_rows)

        preds_sub = preds[sub_idx]
        shap_sub = self.explain(X_win[sub_idx], preds_sub)
        return probs, preds, shap_sub, preds_sub

    def explain(self, X: np.ndarray, classes: np.ndarray) -> np.ndarray:
        """TreeSHAP attributions of every row in X towards the class given for that row: (N, F)."""
        if self.explainer is None:
            self.explainer = shap.TreeExplainer(self.model)
        if len(X) == 0:
            return np.empty((0, X.shape[1]), dtype=np.float32)

        raw_shap = self.explainer.shap_values(X)

        # Normalize SHAP output across shap versions:
        # Either list of C arrays [(M, F), ...] or 3D ndarray (M, F, C)
        if isinstance(raw_shap, list):
            shap_3d = np.stack(raw_shap, axis=-1)  # (M, F, C)
        else:
            shap_3d = np.asarray(raw_shap)
            if shap_3d.ndim == 2:
                shap_3d = np.stack([-shap_3d, shap_3d], axis=-1)

        return shap_3d[np.arange(len(X)), :, np.asarray(classes)].astype(np.float32)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": self.model,
                "label_encoder": self.label_encoder,
                "feature_names": self.feature_names,
                "shap_sample_size": self.shap_sample_size,
                "random_state": self.random_state,
            },
            path,
        )
        logger.info("Saved IDSEngine artifact -> %s", path)

    @classmethod
    def load(cls, path: Path) -> "IDSEngine":
        payload = joblib.load(path)
        obj = cls(
            shap_sample_size=payload["shap_sample_size"],
            random_state=payload["random_state"],
        )
        obj.model = payload["model"]
        obj.label_encoder = payload["label_encoder"]
        obj.feature_names = payload["feature_names"]
        obj.explainer = shap.TreeExplainer(obj.model)
        return obj