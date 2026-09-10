"""Tests for Wave 4 deployment additions: regime→strategy matcher and weekly research."""

import json

import pandas as pd
import pytest

from pyrobot.backtesting.monte_carlo import MonteCarloSimulator
from pyrobot.backtesting.walk_forward import WalkForwardValidator
from pyrobot.features.regime import (
    MarketRegime,
    MarketRegimeDetector,
    RegimeStrategyMatcher,
)

# ── Regime Strategy Matcher ─────────────────────────────────────────────────


class TestRegimeStrategyMatcher:
    def setup_method(self):
        # Ensure built-in strategies are registered.
        import pyrobot.strategies  # noqa: F401

    def test_us_bull_recommends_us_trend(self):
        matcher = RegimeStrategyMatcher()
        assert matcher.recommended_strategy("us", MarketRegime.BULL) == "us_trend"

    def test_metals_bull_recommends_metals_trend(self):
        matcher = RegimeStrategyMatcher()
        assert matcher.recommended_strategy("metals", MarketRegime.BULL) == "metals_trend"

    def test_crypto_bull_recommends_crypto_trend(self):
        matcher = RegimeStrategyMatcher()
        assert matcher.recommended_strategy("crypto", MarketRegime.BULL) == "crypto_trend"

    def test_crypto_bear_recommends_crypto_mean_reversion(self):
        matcher = RegimeStrategyMatcher()
        assert matcher.recommended_strategy("crypto", MarketRegime.BEAR) == "crypto_mean_reversion"

    def test_unknown_market_falls_back_to_none(self):
        matcher = RegimeStrategyMatcher()
        assert matcher.recommended_strategy("unknown", MarketRegime.BULL) is None

    def test_position_scale_for_regimes(self):
        matcher = RegimeStrategyMatcher()
        assert matcher.position_scale(MarketRegime.BULL) == 1.0
        assert matcher.position_scale(MarketRegime.CRISIS) == 0.25
        assert matcher.position_scale(MarketRegime.HIGH_VOLATILITY) < matcher.position_scale(MarketRegime.BULL)

    def test_recommend_returns_full_dict(self):
        from pyrobot.features.regime import RegimeState

        matcher = RegimeStrategyMatcher()
        state = RegimeState(
            regime=MarketRegime.SIDEWAYS,
            confidence=0.7,
            trend_score=0.0,
            volatility_score=0.5,
            recommended_strategy_type="MEAN_REVERSION",
        )
        rec = matcher.recommend("us", state)
        assert rec["market"] == "us"
        assert rec["regime"] == "SIDEWAYS"
        assert rec["recommended_strategy"] == "us_mean_reversion"
        assert 0 < rec["position_scale"] <= 1.0


# ── Regime detector still works on per-market frames ─────────────────────────


class TestRegimeDetectorMultiMarket:
    def _df_for_regime(self, trend: float, volatility: float, n: int = 200):
        rng = __import__("numpy").random.default_rng(7)
        prices = [100.0]
        for i in range(1, n):
            drift = trend * 100.0
            prices.append(prices[-1] * (1 + drift / 100.0 + rng.normal(0, volatility)))
        frame = pd.DataFrame({"close": prices}, index=pd.date_range("2021-01-01", periods=n, freq="D", tz="UTC"))
        # Regime extractor expects standard OHLCV columns.
        frame["open"] = frame["close"] * 0.999
        frame["high"] = frame["close"] * 1.002
        frame["low"] = frame["close"] * 0.998
        frame["volume"] = 1_000_000.0
        return frame

    def test_bull_detected_on_upward_frame(self):
        detector = MarketRegimeDetector()
        df = self._df_for_regime(trend=0.004, volatility=0.005)
        state = detector.get_current_regime(df)
        assert state.regime in (MarketRegime.BULL, MarketRegime.HIGH_VOLATILITY)

    def test_request_eval_happy_path(self):
        # RegimeState carries a recommended strategy type (generic).
        detector = MarketRegimeDetector()
        df = self._df_for_regime(trend=-0.002, volatility=0.02, n=200)
        state = detector.get_current_regime(df)
        assert state.recommended_strategy_type in {
            "TREND_FOLLOWING", "DEFENSIVE_SHORT", "MEAN_REVERSION",
            "REDUCE_SIZE_MOMENTUM", "CAPITAL_PRESERVATION",
        }


# ── Walk-forward + Monte Carlo available per strategy ────────────────────────


class TestStrategyValidationMachinery:
    def test_walk_forward_validator_constructs(self):
        validator = WalkForwardValidator(n_splits=3, train_period_days=20, test_period_days=5, embargo_days=1)
        assert validator.n_splits == 3

    def test_monte_carlo_simulator_runs(self):
        sim = MonteCarloSimulator(n_simulations=10, initial_capital=100_000.0, seed=1)
        report = sim.run([{"pnl": 100.0}, {"pnl": -50.0}, {"pnl": 200.0}] * 5)
        assert report.simulations == 10

    def test_monte_carlo_empty_trades_is_safe(self):
        sim = MonteCarloSimulator(n_simulations=10)
        report = sim.run([])
        assert report.median_return_pct == 0.0


# ── Weekly research benchmark rendering ──────────────────────────────────────


class TestWeeklyResearchBenchmarks:
    def test_benchmark_markdown_renders_table(self):
        from scripts.weekly_research import _benchmark_markdown

        rows = [
            {"strategy": "us_trend", "market": "US", "strategy_return_pct": 10.0,
             "buy_and_hold_return_pct": 5.0, "beat_benchmark": True},
            {"strategy": "metals_trend", "market": "Metals", "strategy_return_pct": 2.0,
             "buy_and_hold_return_pct": 3.0, "beat_benchmark": False},
        ]
        md = _benchmark_markdown(rows)
        assert "| Strategy | Market" in md
        assert "BEAT benchmark" in md
        assert "behind benchmark" in md

    def test_comparison_file_is_valid_json(self):
        from pathlib import Path

        path = Path("data/reports/multi_market_comparison.json")
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            assert "strategies" in data
        else:
            pytest.skip("multi_market_comparison.json not generated yet")
