"""LLM Intelligence and Context Layer — Sentiment, News Classification, and Trade Explainability.

Architecture Rule:
The LLM is strictly an Intelligence & Context Layer. It NEVER owns the execution path
and never directly submits orders to brokers.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pyrobot.logging_config import get_logger

logger = get_logger("llm_context")


class NewsEventType(str, Enum):
    """Categorized market event types."""

    EARNINGS_RELEASE = "EARNINGS_RELEASE"
    GUIDANCE_UPDATE = "GUIDANCE_UPDATE"
    CENTRAL_BANK_MACRO = "CENTRAL_BANK_MACRO"
    REGULATORY_LEGAL = "REGULATORY_LEGAL"
    MERGER_ACQUISITION = "MERGER_ACQUISITION"
    ANALYST_RATING = "ANALYST_RATING"
    GENERAL_NEWS = "GENERAL_NEWS"


@dataclass
class SentimentAnalysis:
    """Structured news sentiment extraction payload."""

    symbol: str
    headline: str
    sentiment_score: float  # -1.0 (extremely bearish) to +1.0 (extremely bullish)
    event_type: NewsEventType
    importance: float       # 0.0 (low) to 1.0 (critical market moving)
    confidence: float
    summary: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "headline": self.headline,
            "sentiment_score": self.sentiment_score,
            "event_type": self.event_type.value,
            "importance": self.importance,
            "confidence": self.confidence,
            "summary": self.summary,
            "timestamp": self.timestamp.isoformat(),
        }


class LLMContextEngine:
    """Intelligence layer for news extraction, sentiment scoring, and trade rationale explanations."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key

    def analyze_headline(
        self,
        symbol: str,
        headline: str,
        content: str = "",
    ) -> SentimentAnalysis:
        """Analyze financial news text and return structured sentiment and event type."""
        # Deterministic financial lexicon scoring for offline / fast path
        text = (headline + " " + content).lower()

        bullish_words = ["beats", "surge", "growth", "record high", "upgrade", "profit up", "strong demand", "partnership"]
        bearish_words = ["misses", "plunge", "loss", "downgrade", "probe", "lawsuit", "slump", "fraud", "halt", "default"]

        bull_count = sum(1 for w in bullish_words if w in text)
        bear_count = sum(1 for w in bearish_words if w in text)

        if bull_count > bear_count:
            sentiment = min(1.0, 0.3 + 0.2 * (bull_count - bear_count))
            event = NewsEventType.EARNINGS_RELEASE if "earnings" in text or "beats" in text else NewsEventType.GENERAL_NEWS
            summary = f"Bullish sentiment detected ({bull_count} positive triggers)"
        elif bear_count > bull_count:
            sentiment = max(-1.0, -0.3 - 0.2 * (bear_count - bull_count))
            event = NewsEventType.REGULATORY_LEGAL if "probe" in text or "lawsuit" in text else NewsEventType.GENERAL_NEWS
            summary = f"Bearish sentiment detected ({bear_count} negative triggers)"
        else:
            sentiment = 0.0
            event = NewsEventType.GENERAL_NEWS
            summary = "Neutral sentiment"

        return SentimentAnalysis(
            symbol=symbol.upper(),
            headline=headline,
            sentiment_score=sentiment,
            event_type=event,
            importance=0.5 if abs(sentiment) < 0.5 else 0.8,
            confidence=0.85,
            summary=summary,
        )

    def explain_trade_decision(
        self,
        symbol: str,
        signal_reason: str,
        regime_name: str,
        confidence: float,
        risk_decision_reason: str,
        approved: bool,
    ) -> str:
        """Generate human-readable audit commentary explaining why a trade was approved or rejected."""
        status = "EXECUTED" if approved else "REJECTED"
        return (
            f"Trade Decision [{status}] for {symbol}:\n"
            f"  - Market Regime: {regime_name}\n"
            f"  - Signal Rationale: {signal_reason} (Confidence: {confidence:.1%})\n"
            f"  - Risk Governance: {risk_decision_reason}"
        )
