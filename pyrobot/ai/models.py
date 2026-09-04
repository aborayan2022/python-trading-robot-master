"""Quantitative Machine Learning Estimators and Forecast Models.

All estimators are dependency-free (NumPy only) and intentionally simple:
regularized linear models trained by gradient descent / normal equations.
They are honest baselines, not boosted trees or neural networks — the class
names and docstrings say exactly what each model is.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, cast

import numpy as np
import pandas as pd

from pyrobot.logging_config import get_logger

logger = get_logger("ai_models")


class BaseQuantModel(ABC):
    """Abstract interface for all quantitative ML models."""

    #: Short type tag stored in ModelRegistry metadata and artifact files.
    model_type: str = "base"

    def __init__(self, model_id: str, version: str = "v1.0") -> None:
        self.model_id = model_id
        self.version = version
        self.is_fitted: bool = False
        self.feature_names: List[str] = []

    @abstractmethod
    def fit(self, X: pd.DataFrame, y: pd.Series) -> "BaseQuantModel":
        """Fit model on feature matrix X and target y."""
        ...

    @abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Generate predictions for feature matrix X."""
        ...

    @abstractmethod
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Generate probability estimates for classification targets."""
        ...

    @abstractmethod
    def save(self, path: str | Path) -> None:
        """Persist fitted parameters to a .npz artifact (no arbitrary pickling)."""
        ...

    @classmethod
    @abstractmethod
    def load(cls, path: str | Path) -> "BaseQuantModel":
        """Restore a model from a .npz artifact written by save()."""
        ...


class LogisticDirectionModel(BaseQuantModel):
    """Directional price-movement classifier: L2-regularized logistic regression.

    Predicts P(return > threshold) over the target forward horizon, trained by
    full-batch gradient descent on standardized features with early stopping on
    the max-gradient convergence tolerance.
    """

    model_type = "logistic_direction"

    def __init__(
        self,
        model_id: str = "logistic_direction",
        version: str = "v1.0",
        n_iterations: int = 1000,
        learning_rate: float = 0.1,
        l2_reg: float = 0.01,
        tol: float = 1e-6,
    ) -> None:
        super().__init__(model_id=model_id, version=version)
        self.n_iterations = n_iterations
        self.learning_rate = learning_rate
        self.l2_reg = l2_reg
        self.tol = tol
        self.weights: Optional[np.ndarray] = None
        self.bias: float = 0.0
        self.n_iter_run: int = 0
        # |w| of the de-standardized linear model — linear coefficient weights,
        # NOT tree-based importances.
        self.feature_importances_: Dict[str, float] = {}

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "LogisticDirectionModel":
        """Fit L2-regularized logistic regression via gradient descent."""
        self.feature_names = list(X.columns)
        X_mat = X.values.astype(np.float64)
        y_vec = y.values.astype(np.float64)

        # Standardize features for stable gradients (de-standardized on fit end)
        mean = np.nanmean(X_mat, axis=0)
        std = np.nanstd(X_mat, axis=0)
        std[std == 0] = 1.0
        X_norm = np.nan_to_num((X_mat - mean) / std)

        n_samples, n_features = X_norm.shape
        w = np.zeros(n_features)
        b = 0.0

        self.n_iter_run = 0
        for _ in range(self.n_iterations):
            self.n_iter_run += 1
            logits = np.dot(X_norm, w) + b
            probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -20.0, 20.0)))
            errors = probs - y_vec
            dw = (np.dot(X_norm.T, errors) / n_samples) + (self.l2_reg * w)
            db = np.mean(errors)
            w -= self.learning_rate * dw
            b -= self.learning_rate * db
            if max(float(np.max(np.abs(dw))), float(abs(db))) < self.tol:
                break

        # De-standardize so predict() works on raw (unnormalized) features
        self.weights = w / std
        self.bias = b - float(np.sum((w * mean) / std))
        self.is_fitted = True

        abs_w = np.abs(self.weights)
        total_w = np.sum(abs_w) if np.sum(abs_w) > 0 else 1.0
        self.feature_importances_ = {
            f: float(w_val / total_w) for f, w_val in zip(self.feature_names, abs_w)
        }
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return probability matrix [[P(down), P(up)], ...]."""
        if not self.is_fitted or self.weights is None:
            raise RuntimeError("Model must be fitted before calling predict_proba")

        X_mat = np.nan_to_num(X[self.feature_names].values.astype(np.float64))
        logits = np.dot(X_mat, self.weights) + self.bias
        p_up = 1.0 / (1.0 + np.exp(-np.clip(logits, -20.0, 20.0)))
        p_down = 1.0 - p_up
        return np.column_stack((p_down, p_up))

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Return binary prediction (0 = down/flat, 1 = up)."""
        probs = self.predict_proba(X)
        return (probs[:, 1] >= 0.5).astype(int)

    def save(self, path: str | Path) -> None:
        """Persist fitted parameters to a .npz artifact."""
        if not self.is_fitted or self.weights is None:
            raise RuntimeError("Model must be fitted before save()")
        np.savez(
            path,
            model_type=self.model_type,
            model_id=self.model_id,
            version=self.version,
            feature_names="|".join(self.feature_names),  # pickle-free string
            weights=self.weights,
            bias=np.array([self.bias]),
            n_iter_run=np.array([self.n_iter_run]),
            is_fitted=np.array([self.is_fitted]),
        )

    @classmethod
    def load(cls, path: str | Path) -> "LogisticDirectionModel":
        """Restore a fitted model from a .npz artifact."""
        with np.load(path, allow_pickle=False) as data:
            if str(data["model_type"]) != cls.model_type:
                raise ValueError(
                    f"Artifact type mismatch: expected {cls.model_type}, got {data['model_type']}"
                )
            model = cls(model_id=str(data["model_id"]), version=str(data["version"]))
            model.feature_names = str(data["feature_names"]).split("|")
            model.weights = data["weights"].astype(np.float64)
            model.bias = float(data["bias"][0])
            model.n_iter_run = int(data["n_iter_run"][0])
            model.is_fitted = bool(data["is_fitted"][0])
        return model


# Backward-compatible alias. The old name claimed gradient boosting; the
# implementation was always regularized logistic regression — use the new name.
GBDTDirectionClassifier = LogisticDirectionModel


class VolatilityForecaster(BaseQuantModel):
    """Ridge-regularized OLS regression predicting forward realized volatility."""

    model_type = "volatility_forecaster"

    def __init__(
        self,
        model_id: str = "vol_forecaster",
        version: str = "v1.0",
        l2_reg: float = 0.01,
    ) -> None:
        super().__init__(model_id=model_id, version=version)
        self.l2_reg = l2_reg
        self.coefficients: Optional[np.ndarray] = None
        self.intercept: float = 0.0

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "VolatilityForecaster":
        self.feature_names = list(X.columns)
        X_mat = np.nan_to_num(X.values.astype(np.float64))
        y_vec = np.nan_to_num(y.values.astype(np.float64))

        n_features = X_mat.shape[1]
        reg_matrix = self.l2_reg * np.eye(n_features)
        A = np.dot(X_mat.T, X_mat) + reg_matrix
        b = np.dot(X_mat.T, y_vec)
        self.coefficients = np.linalg.solve(A, b)
        self.intercept = float(np.mean(y_vec) - np.mean(np.dot(X_mat, self.coefficients)))
        self.is_fitted = True
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if not self.is_fitted or self.coefficients is None:
            raise RuntimeError("Model must be fitted before predict")
        X_mat = np.nan_to_num(X[self.feature_names].values.astype(np.float64))
        preds = np.dot(X_mat, self.coefficients) + self.intercept
        # Volatility must be positive
        return cast(np.ndarray, np.maximum(0.001, preds))

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError("VolatilityForecaster is a continuous regression model")

    def save(self, path: str | Path) -> None:
        if not self.is_fitted or self.coefficients is None:
            raise RuntimeError("Model must be fitted before save()")
        np.savez(
            path,
            model_type=self.model_type,
            model_id=self.model_id,
            version=self.version,
            feature_names="|".join(self.feature_names),  # pickle-free string
            coefficients=self.coefficients,
            intercept=np.array([self.intercept]),
            is_fitted=np.array([self.is_fitted]),
        )

    @classmethod
    def load(cls, path: str | Path) -> "VolatilityForecaster":
        with np.load(path, allow_pickle=False) as data:
            if str(data["model_type"]) != cls.model_type:
                raise ValueError(
                    f"Artifact type mismatch: expected {cls.model_type}, got {data['model_type']}"
                )
            model = cls(model_id=str(data["model_id"]), version=str(data["version"]))
            model.feature_names = str(data["feature_names"]).split("|")
            model.coefficients = data["coefficients"].astype(np.float64)
            model.intercept = float(data["intercept"][0])
            model.is_fitted = bool(data["is_fitted"][0])
        return model


def _lazy_import_lightgbm():
    """Lazy import for OptionalLightGBMDirectionModel to avoid hard dependency."""
    from pyrobot.ai.training import OptionalLightGBMDirectionModel
    return OptionalLightGBMDirectionModel


MODEL_TYPES: Dict[str, type] = {
    LogisticDirectionModel.model_type: LogisticDirectionModel,
    VolatilityForecaster.model_type: VolatilityForecaster,
    "lightgbm_direction": _lazy_import_lightgbm,  # resolved lazily
}


def model_class_for_type(model_type: str) -> type[BaseQuantModel]:
    """Map a registry model_type tag to its model class."""
    cls_or_factory = MODEL_TYPES.get(model_type)
    if cls_or_factory is None:
        raise ValueError(f"Unknown model_type '{model_type}'. Known: {list(MODEL_TYPES)}")
    # Resolve lazy import factories
    if callable(cls_or_factory) and not isinstance(cls_or_factory, type):
        return cls_or_factory()
    return cls_or_factory
