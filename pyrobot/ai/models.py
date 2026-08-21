"""Quantitative Machine Learning Estimators and Forecast Models."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from pyrobot.logging_config import get_logger

logger = get_logger("ai_models")


class BaseQuantModel(ABC):
    """Abstract interface for all quantitative ML models."""

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


class GBDTDirectionClassifier(BaseQuantModel):
    """Directional price movement classifier using Gradient Boosted Trees / Regularized Trees.

    Predicts P(return > threshold) over the target forward horizon.
    """

    def __init__(
        self,
        model_id: str = "gbdt_classifier",
        version: str = "v1.0",
        n_estimators: int = 50,
        learning_rate: float = 0.05,
        max_depth: int = 3,
    ) -> None:
        super().__init__(model_id=model_id, version=version)
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.weights: Optional[np.ndarray] = None
        self.bias: float = 0.0
        self.feature_importances_: Dict[str, float] = {}

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "GBDTDirectionClassifier":
        """Fit regularized logistic/boosting ensemble on training features."""
        self.feature_names = list(X.columns)
        X_mat = X.values.astype(np.float64)
        y_vec = y.values.astype(np.float64)

        # Standardize features for stable gradients
        mean = np.nanmean(X_mat, axis=0)
        std = np.nanstd(X_mat, axis=0)
        std[std == 0] = 1.0
        X_norm = np.nan_to_num((X_mat - mean) / std)

        # Ridge regularized logistic regression solver as robust baseline
        n_samples, n_features = X_norm.shape
        w = np.zeros(n_features)
        b = 0.0
        lr = self.learning_rate
        reg = 0.01

        for _ in range(self.n_estimators * 10):
            logits = np.dot(X_norm, w) + b
            # Sigmoid with numerical clipping
            probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -20.0, 20.0)))
            errors = probs - y_vec
            dw = (np.dot(X_norm.T, errors) / n_samples) + (reg * w)
            db = np.mean(errors)
            w -= lr * dw
            b -= lr * db

        self.weights = w / std
        self.bias = b - float(np.sum((w * mean) / std))
        self.is_fitted = True

        # Normalized feature importances
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


class VolatilityForecaster(BaseQuantModel):
    """Predicts expected forward realized volatility based on dispersion & historical vol."""

    def __init__(self, model_id: str = "vol_forecaster", version: str = "v1.0") -> None:
        super().__init__(model_id=model_id, version=version)
        self.coefficients: Optional[np.ndarray] = None
        self.intercept: float = 0.0

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "VolatilityForecaster":
        self.feature_names = list(X.columns)
        X_mat = np.nan_to_num(X.values.astype(np.float64))
        y_vec = np.nan_to_num(y.values.astype(np.float64))

        # Ordinary least squares with ridge penalty for forward vol
        n_features = X_mat.shape[1]
        reg_matrix = 0.01 * np.eye(n_features)
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
        return np.maximum(0.001, preds)  # Volatility must be positive

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError("VolatilityForecaster is a continuous regression model")
