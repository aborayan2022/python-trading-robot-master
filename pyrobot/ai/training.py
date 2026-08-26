"""Production training pipeline and model approval gates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, List, Optional, cast

import numpy as np
import pandas as pd

from pyrobot.ai.calibration import IsotonicCalibrator
from pyrobot.ai.labels import LabelBuilder
from pyrobot.ai.models import BaseQuantModel, LogisticDirectionModel
from pyrobot.ai.registry import ModelMetadata, ModelRegistry, ModelStatus
from pyrobot.backtesting.walk_forward import run_walk_forward
from pyrobot.data.base import DataFrequency, MarketDataProvider
from pyrobot.features.engine import FeatureEngine


@dataclass
class TrainingGateConfig:
    """Minimum governance thresholds before a model can become champion."""

    min_oos_accuracy_edge: float = 0.01
    min_oos_samples: int = 100
    max_calibration_error: float = 0.15


def accuracy_metric(y_true: pd.Series, y_pred: np.ndarray) -> float:
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(y_pred, dtype=int)
    if len(y) == 0:
        return 0.0
    return float(np.mean(y == p))


def buy_and_hold_direction_baseline(labels: pd.Series) -> float:
    """Baseline that always predicts upward movement."""
    return accuracy_metric(labels, np.ones(len(labels), dtype=int))


def sma_direction_baseline(frame: pd.DataFrame, labels: pd.Series, fast: int = 20, slow: int = 50) -> float:
    close = frame["close"].astype(float)
    if isinstance(frame.index, pd.MultiIndex):
        fast_ma = close.groupby(level=0).transform(lambda s: s.rolling(fast).mean())
        slow_ma = close.groupby(level=0).transform(lambda s: s.rolling(slow).mean())
        preds = (fast_ma > slow_ma).astype(int)
    else:
        preds = (close.rolling(fast).mean() > close.rolling(slow).mean()).astype(int)
    aligned = preds.loc[labels.index].fillna(1).to_numpy(dtype=int)
    return accuracy_metric(labels, aligned)


class OptionalLightGBMDirectionModel(LogisticDirectionModel):
    """LightGBM classifier behind the BaseQuantModel interface when installed.

    If lightgbm is unavailable, construction raises ImportError; the training
    pipeline falls back to LogisticDirectionModel unless the caller explicitly
    requires this model.
    """

    model_type = "lightgbm_direction"

    def __init__(self, model_id: str = "lightgbm_direction", version: str = "v1.0", **params) -> None:
        BaseQuantModel.__init__(self, model_id=model_id, version=version)
        self.params = params or {"n_estimators": 100, "learning_rate": 0.05, "num_leaves": 15}
        self._model: Any = None

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "OptionalLightGBMDirectionModel":
        try:
            from lightgbm import LGBMClassifier  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError("Install python-trading-robot[ml] to use LightGBM") from exc
        self.feature_names = list(X.columns)
        self._model = LGBMClassifier(**self.params)
        self._model.fit(X.fillna(0.0), y.astype(int))
        self.is_fitted = True
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("Model must be fitted before predict")
        return cast(np.ndarray, np.asarray(self._model.predict(X[self.feature_names].fillna(0.0)), dtype=int))

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("Model must be fitted before predict_proba")
        return cast(np.ndarray, np.asarray(self._model.predict_proba(X[self.feature_names].fillna(0.0))))

    def save(self, path: str | Path) -> None:
        raise RuntimeError("LightGBM artifact persistence requires joblib and is not enabled by default")

    @classmethod
    def load(cls, path: str | Path) -> "OptionalLightGBMDirectionModel":
        raise RuntimeError("LightGBM artifact loading is not enabled by default")


def build_training_frame(
    provider: MarketDataProvider,
    symbols: List[str],
    start: datetime,
    end: datetime,
    *,
    frequency: DataFrequency = DataFrequency.MINUTE_1,
) -> pd.DataFrame:
    """Download and combine historical candles for a symbol universe."""
    frames = []
    for symbol in symbols:
        candles = provider.get_historical_candles(symbol, start, end, frequency)
        df = provider.to_dataframe(candles)
        if df.empty:
            continue
        df["symbol"] = symbol.upper()
        frames.append(df)
    if not frames:
        raise ValueError("No historical candles returned for training")
    combined = pd.concat(frames).sort_index()
    return cast(pd.DataFrame, combined)


def _features_and_labels_by_symbol(
    market_data: pd.DataFrame,
    feature_engine: FeatureEngine,
    *,
    horizon: int,
    threshold: float,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    if "symbol" not in market_data.columns:
        features = feature_engine.extract_features(market_data)
        labels = LabelBuilder().direction_labels(market_data, horizon=horizon, threshold=threshold)
        labels, features = LabelBuilder.drop_unlabeled(labels, features)
        return features, labels.astype(int), market_data.loc[labels.index]

    feature_pieces = []
    label_pieces = []
    price_pieces = []
    for symbol, group in market_data.groupby("symbol", sort=True):
        g = group.drop(columns=["symbol"]).sort_index()
        feats = feature_engine.extract_features(g)
        labels = LabelBuilder().direction_labels(g, horizon=horizon, threshold=threshold)
        labels, feats = LabelBuilder.drop_unlabeled(labels, feats)
        idx = pd.MultiIndex.from_arrays(
            [[str(symbol)] * len(feats), feats.index],
            names=["symbol", "datetime"],
        )
        feats = feats.copy()
        feats.index = idx
        labels = labels.copy().astype(int)
        labels.index = idx
        prices = g.loc[pd.Index(idx.get_level_values("datetime"))].copy()
        prices.index = idx
        feature_pieces.append(feats)
        label_pieces.append(labels)
        price_pieces.append(prices)
    if not feature_pieces:
        raise ValueError("No labeled feature rows were produced")
    return pd.concat(feature_pieces).sort_index(), pd.concat(label_pieces).sort_index(), pd.concat(price_pieces).sort_index()


def train_direction_champion_candidate(
    market_data: pd.DataFrame,
    registry: ModelRegistry,
    *,
    model_id: str = "alpaca_logistic_direction",
    version: str = "v1.0",
    feature_engine: Optional[FeatureEngine] = None,
    model_factory: Optional[Callable[[], BaseQuantModel]] = None,
    horizon: int = 5,
    threshold: float = 0.0,
    gate: Optional[TrainingGateConfig] = None,
    report_path: Optional[str | Path] = None,
) -> dict:
    """Train, evaluate, gate, and register a direction model candidate."""
    gate = gate or TrainingGateConfig()
    feature_engine = feature_engine or FeatureEngine()
    model_factory = model_factory or (lambda: LogisticDirectionModel(model_id=model_id, version=version))

    features, labels, aligned_prices = _features_and_labels_by_symbol(
        market_data,
        feature_engine,
        horizon=horizon,
        threshold=threshold,
    )
    clean = features.replace([np.inf, -np.inf], np.nan).dropna()
    labels = labels.loc[clean.index].astype(int)
    if len(clean) < gate.min_oos_samples:
        raise ValueError(f"Insufficient labeled training rows: {len(clean)} < {gate.min_oos_samples}")

    result = run_walk_forward(
        clean,
        labels,
        model_factory=model_factory,
        train_fn=lambda model, x, y: model.fit(x, y),
        predict_fn=lambda model, x: model.predict(x),
        metric_fn=accuracy_metric,
        n_splits=3,
        train_period_days=20,
        test_period_days=5,
        embargo_days=1,
        expanding=True,
    )
    bh = buy_and_hold_direction_baseline(labels)
    sma = sma_direction_baseline(aligned_prices.loc[labels.index], labels)

    fitted = model_factory()
    fitted.fit(clean, labels)
    proba = fitted.predict_proba(clean)[:, 1]
    calibrator = IsotonicCalibrator().fit(proba, labels)
    calibration = calibrator.report(proba, labels)

    approved = (
        len(result.oos_predictions) >= gate.min_oos_samples
        and result.oos_score >= max(bh, sma) + gate.min_oos_accuracy_edge
        and calibration["expected_calibration_error"] <= gate.max_calibration_error
    )
    status = ModelStatus.CHALLENGER if approved else ModelStatus.CANDIDATE
    metadata = ModelMetadata(
        model_id=model_id,
        version=version,
        model_type=fitted.model_type,
        target_variable=f"dir_{horizon}",
        features=list(clean.columns),
        training_start=str(market_data.index.min()),
        training_end=str(market_data.index.max()),
        status=status,
        oos_metrics={
            "oos_accuracy": float(result.oos_score),
            "buy_hold_accuracy": float(bh),
            "sma_accuracy": float(sma),
            "expected_calibration_error": float(calibration["expected_calibration_error"]),
            "oos_samples": float(len(result.oos_predictions)),
        },
        hyperparameters={"horizon": horizon, "threshold": threshold},
        description="Alpaca production candidate; champion promotion requires explicit review.",
    )
    registry.register_model(metadata, model=fitted)
    report = {
        "approved_for_challenger": approved,
        "walk_forward": result.summary(),
        "baselines": {"buy_and_hold": bh, "sma": sma},
        "calibration": calibration,
        "model": metadata.to_dict(),
    }
    if report_path is not None:
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report
