"""Signal engine combining quant model forecasts and market regime into Signals.

Decision rules (single explicit threshold, no redundant conditions):
- Entry BUY requires prob_up >= min_probability in BULL/SIDEWAYS regimes.
- Entry SELL_SHORT requires prob_up <= 1 - min_probability in BEAR/HIGH_VOLATILITY.
- CRISIS always returns NO_TRADE (risk-off halt).
- Exit: a held long exits (SELL) when prob_up < exit_threshold; a held short
  covers (BUY_TO_COVER) when prob_up > 1 - exit_threshold.

If fitted models are not supplied, the engine lazily loads the registry's
champion models (direction + volatility) on first use.  When a calibrator
is registered alongside the champion, it is applied to raw probabilities
before threshold comparison (WO-1).
"""

from datetime import datetime, timezone
from typing import Dict, Optional

import numpy as np
import pandas as pd

from pyrobot.ai.calibration import IsotonicCalibrator
from pyrobot.ai.models import LogisticDirectionModel, VolatilityForecaster
from pyrobot.ai.registry import ModelRegistry
from pyrobot.features.regime import MarketRegime, MarketRegimeDetector
from pyrobot.logging_config import get_logger
from pyrobot.models.signal import Signal, SignalAction

logger = get_logger("ensemble_engine")

_ACTIONABLE = {
    SignalAction.BUY,
    SignalAction.SELL,
    SignalAction.SELL_SHORT,
    SignalAction.BUY_TO_COVER,
}


class EnsembleSignalEngine:
    """Converts model forecasts and regime state into unified trading Signals."""

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        direction_model: Optional[LogisticDirectionModel] = None,
        volatility_model: Optional[VolatilityForecaster] = None,
        regime_detector: Optional[MarketRegimeDetector] = None,
        calibrator: Optional[IsotonicCalibrator] = None,
        min_probability: float = 0.80,
        exit_probability: float = 0.45,
        default_volatility: float = 0.02,
    ) -> None:
        if not 0.5 < min_probability <= 1.0:
            raise ValueError("min_probability must be in (0.5, 1.0]")
        if not 0.0 < exit_probability < 0.5:
            raise ValueError("exit_probability must be in (0, 0.5)")
        self.registry = registry
        self.direction_model = direction_model
        self.volatility_model = volatility_model
        self.regime_detector = regime_detector or MarketRegimeDetector()
        self.calibrator = calibrator
        self.min_probability = min_probability
        self.exit_probability = exit_probability
        self.default_volatility = default_volatility
        self._registry_models_loaded = False

    def _ensure_models_loaded(self) -> None:
        """Lazily load champion models and calibrator from the registry."""
        if self._registry_models_loaded or self.registry is None:
            return
        self._registry_models_loaded = True
        try:
            champion = self.registry.get_champion()
        except Exception as exc:  # pragma: no cover - registry failures are non-fatal
            logger.warning("Registry champion lookup failed: %s", exc)
            return
        if champion is None:
            return
        try:
            if self.direction_model is None and champion.model_type == LogisticDirectionModel.model_type:
                loaded = self.registry.load_model(champion.model_id, champion.version)
                assert isinstance(loaded, LogisticDirectionModel)
                self.direction_model = loaded
                logger.info("Loaded champion direction model %s:%s", champion.model_id, champion.version)
        except Exception as exc:
            logger.warning("Failed to load champion direction artifact: %s", exc)
        # WO-1: Load calibrator when available
        try:
            if self.calibrator is None:
                loaded_cal = self.registry.load_calibrator(champion.model_id, champion.version)
                if loaded_cal is not None:
                    self.calibrator = loaded_cal
                    logger.info("Loaded calibrator for champion %s:%s", champion.model_id, champion.version)
                else:
                    logger.warning(
                        "Champion loaded WITHOUT calibrator — thresholds operate on uncalibrated probabilities"
                    )
        except Exception as exc:
            logger.warning("Failed to load calibrator: %s", exc)
        # Volatility model: fall back to scanning for a champion/any registered forecaster
        try:
            if self.volatility_model is None:
                for meta in self.registry.list_models():
                    if meta.model_type == VolatilityForecaster.model_type:
                        loaded = self.registry.load_model(meta.model_id, meta.version)
                        assert isinstance(loaded, VolatilityForecaster)
                        self.volatility_model = loaded
                        break
        except Exception as exc:
            logger.warning("Failed to load volatility artifact: %s", exc)

    def generate_signal(
        self,
        symbol: str,
        features_df: pd.DataFrame,
        position_state: Optional[Dict[str, float]] = None,
        strategy_id: str = "ensemble_quant_v1",
    ) -> Signal:
        """Generate a risk-calibrated Signal from model forecasts and regime state.

        Args:
            symbol: Ticker the signal applies to.
            features_df: Feature history (backward-looking only); the last row is "now".
            position_state: Optional map symbol -> net quantity, enabling exit
                signals for held positions.
            strategy_id: Strategy tag attached to the produced Signal.
        """
        if features_df.empty:
            return Signal(
                symbol=symbol,
                action=SignalAction.NO_TRADE,
                confidence=0.0,
                probability=0.5,
                reason="Empty features DataFrame",
                strategy_id=strategy_id,
            )

        self._ensure_models_loaded()

        # 1. Market Regime Evaluation — CRISIS is a hard risk-off halt.
        regime_state = self.regime_detector.detect(features_df)
        regime = regime_state.regime

        if regime == MarketRegime.CRISIS:
            return Signal(
                symbol=symbol,
                action=SignalAction.NO_TRADE,
                confidence=1.0,
                probability=0.5,
                expected_risk=regime_state.volatility_score * 0.05,
                reason="Market regime is CRISIS — Risk-off halt",
                strategy_id=strategy_id,
            )

        # 2. Direction probability from the model (0.5 = no model / no edge).
        prob_up = 0.5
        model_id = "default_baseline"
        if self.direction_model is not None and self.direction_model.is_fitted:
            probs = self.direction_model.predict_proba(features_df.iloc[[-1]])
            prob_up = float(probs[0, 1])
            model_id = f"{self.direction_model.model_id}:{self.direction_model.version}"

        # WO-1: Apply calibrator when available — all downstream consumers
        # (thresholds, confidence, expected_return) use the calibrated value.
        if self.calibrator is not None and self.calibrator.is_fitted:
            prob_up = float(self.calibrator.transform(np.array([prob_up]))[0])

        # 3. Expected forward volatility (model forecast or default).
        exp_vol = self.default_volatility
        if self.volatility_model is not None and self.volatility_model.is_fitted:
            exp_vol = float(self.volatility_model.predict(features_df.iloc[[-1]])[0])

        # 4. Confidence & expected return (linear rescale, NOT a calibration).
        confidence = float(abs(prob_up - 0.5) * 2.0)
        float((prob_up - 0.5) * 2.0 * exp_vol)

        # 5. Exit logic first: managing an open position beats opening a new one.
        net_position = (position_state or {}).get(symbol, 0.0)
        if net_position > 0 and prob_up < self.exit_probability:
            return self._signal(
                symbol, SignalAction.SELL, prob_up, confidence, exp_vol, model_id, strategy_id,
                reason=f"Exit long: P(up)={prob_up:.1%} below exit threshold {self.exit_probability:.0%}",
            )
        if net_position < 0 and prob_up > (1.0 - self.exit_probability):
            return self._signal(
                symbol, SignalAction.BUY_TO_COVER, prob_up, confidence, exp_vol, model_id, strategy_id,
                reason=f"Cover short: P(up)={prob_up:.1%} above cover threshold {1 - self.exit_probability:.0%}",
            )

        # 6. Entry logic: single explicit probability threshold, regime-gated.
        action = SignalAction.NO_TRADE
        reason = f"Regime={regime.value}, P(up)={prob_up:.2%} below entry threshold {self.min_probability:.0%}"

        if prob_up >= self.min_probability:
            if regime in (MarketRegime.BULL, MarketRegime.SIDEWAYS):
                action = SignalAction.BUY
                reason = f"High conviction bullish signal ({prob_up:.1%}) in {regime.value} regime"
        elif prob_up <= (1.0 - self.min_probability):
            if regime in (MarketRegime.BEAR, MarketRegime.HIGH_VOLATILITY):
                action = SignalAction.SELL_SHORT
                reason = f"High conviction bearish signal ({prob_up:.1%}) in {regime.value} regime"

        return self._signal(symbol, action, prob_up, confidence, exp_vol, model_id, strategy_id, reason)

    @staticmethod
    def _signal(
        symbol: str,
        action: SignalAction,
        prob_up: float,
        confidence: float,
        exp_vol: float,
        model_id: str,
        strategy_id: str,
        reason: str,
    ) -> Signal:
        return Signal(
            symbol=symbol,
            action=action,
            probability=prob_up,
            confidence=confidence,
            expected_return=float((prob_up - 0.5) * 2.0 * exp_vol) if action in _ACTIONABLE else None,
            expected_risk=exp_vol,
            strategy_id=strategy_id,
            model_id=model_id,
            reason=reason,
            timestamp=datetime.now(timezone.utc),
        )
