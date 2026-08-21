"""Ensemble Signal Engine combining Quant Models, Market Regimes, and Confidence Calibration."""

from datetime import datetime, timezone
from typing import Dict, List, Optional
import pandas as pd

from pyrobot.ai.models import GBDTDirectionClassifier, VolatilityForecaster
from pyrobot.ai.registry import ModelRegistry
from pyrobot.features.regime import MarketRegime, MarketRegimeDetector
from pyrobot.logging_config import get_logger
from pyrobot.models.signal import Signal, SignalAction

logger = get_logger("ensemble_engine")


class EnsembleSignalEngine:
    """Ensemble coordinator converting AI forecasts and market regimes into unified Signals."""

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        direction_model: Optional[GBDTDirectionClassifier] = None,
        volatility_model: Optional[VolatilityForecaster] = None,
        regime_detector: Optional[MarketRegimeDetector] = None,
        min_confidence_threshold: float = 0.60,
    ) -> None:
        self.registry = registry
        self.direction_model = direction_model
        self.volatility_model = volatility_model
        self.regime_detector = regime_detector or MarketRegimeDetector()
        self.min_confidence = min_confidence_threshold

    def generate_signal(
        self,
        symbol: str,
        features_df: pd.DataFrame,
        current_price: float,
        strategy_id: str = "ensemble_quant_v1",
    ) -> Signal:
        """Generate a risk-calibrated Signal from the ensemble of models and regime state."""
        if features_df.empty:
            return Signal(
                symbol=symbol,
                action=SignalAction.NO_TRADE,
                confidence=0.0,
                probability=0.5,
                reason="Empty features DataFrame",
                strategy_id=strategy_id,
            )

        # 1. Market Regime Evaluation
        regime_state = self.regime_detector.detect(features_df)
        regime = regime_state.regime

        # In Crisis regime -> Mandatory Risk-Off / No Trade
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

        # 2. Direction Probability
        prob_up = 0.5
        model_id = "default_baseline"
        if self.direction_model and self.direction_model.is_fitted:
            probs = self.direction_model.predict_proba(features_df.iloc[[-1]])
            prob_up = float(probs[0, 1])
            model_id = f"{self.direction_model.model_id}:{self.direction_model.version}"

        # 3. Expected Forward Volatility / Risk
        exp_vol = 0.02  # 2% baseline
        if self.volatility_model and self.volatility_model.is_fitted:
            exp_vol = float(self.volatility_model.predict(features_df.iloc[[-1]])[0])

        # 4. Confidence & Expected Return Estimation
        # Confidence measures directional certainty away from random walk 0.5
        confidence = float(abs(prob_up - 0.5) * 2.0)
        expected_return = float((prob_up - 0.5) * 2.0 * exp_vol)

        # 5. Regime-aware Action Selection
        action = SignalAction.NO_TRADE
        reason = f"Regime={regime.value}, P(up)={prob_up:.2%}, Conf={confidence:.2%}"

        if confidence >= self.min_confidence:
            if prob_up > 0.55:
                if regime in (MarketRegime.BULL, MarketRegime.SIDEWAYS):
                    action = SignalAction.BUY
                    reason = f"High conviction bullish signal ({prob_up:.1%}) in {regime.value} regime"
            elif prob_up < 0.45:
                if regime in (MarketRegime.BEAR, MarketRegime.HIGH_VOLATILITY):
                    action = SignalAction.SELL_SHORT
                    reason = f"High conviction bearish signal ({prob_up:.1%}) in {regime.value} regime"

        return Signal(
            symbol=symbol,
            action=action,
            probability=prob_up,
            confidence=confidence,
            expected_return=expected_return,
            expected_risk=exp_vol,
            strategy_id=strategy_id,
            model_id=model_id,
            reason=reason,
            timestamp=datetime.now(timezone.utc),
        )
