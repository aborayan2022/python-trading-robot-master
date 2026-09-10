# Wave 0: Mean Reversion Strategy — Logic Before Code

**Strategy:** Mean Reversion
**Direction:** Long + Short (all markets)
**Core Idea:** "Prices that deviate far from their mean tend to revert."

---

## The Hypothesis

Asset prices oscillate around a **fair value** (mean). When price deviates
significantly from this mean, it creates an opportunity:
- **Below mean** → price is "cheap" → BUY (expect reversion up).
- **Above mean** → price is "expensive" → SELL (expect reversion down).

This works because:
1. **Profit-taking** — extreme moves attract sellers (or buyers).
2. **Arbitrage** — participants exploit mispricing.
3. **Rubber-band effect** — prices stretch but snap back.

## The Rules

### Entry (BUY — mean reversion long):

| Rule | Condition | Purpose |
|------|-----------|---------|
| Oversold RSI | `RSI(14) < 30` | Price is statistically oversold |
| Below lower Bollinger | `close < BB_lower(20, 2)` | Price is 2σ below mean |
| Volume spike | `volume > 2× avg_volume` | Capitulation selling |

### Entry (SELL SHORT — mean reversion short):

| Rule | Condition | Purpose |
|------|-----------|---------|
| Overbought RSI | `RSI(14) > 70` | Price is statistically overbought |
| Above upper Bollinger | `close > BB_upper(20, 2)` | Price is 2σ above mean |
| Volume spike | `volume > 2× avg_volume` | Euphoric buying |

### Exit — reversion target:

| Rule | Condition | Purpose |
|------|-----------|---------|
| Mean reversion | `close crosses SMA(20)` | Price returned to mean |
| Time stop | `bars_held > 10` | Exit if reversion is too slow |
| Stop loss | `loss > 2%` | Cut losses if mean doesn't hold |

### Why This Works

- Markets are not always trending — they spend ~60% of time in ranges.
- RSI and Bollinger Bands are mathematically grounded statistical measures.
- Volume confirmation adds a behavioral signal (capitulation/euphoria).
- Mean reversion has higher win rates than trend following (but lower R:R).

### Why This Can Fail

- **Strong trends** — mean reversion fights the trend and loses.
- **Structural breaks** — the "mean" itself shifts (earnings, regime change).
- **Black swans** — extreme events don't revert quickly.
- **Whipsaws** — many small losses while waiting for the big reversion.

## Relation to Other Strategies

| Strategy | Relationship |
|----------|-------------|
| Trend Following | Opposite — rides trends instead of fading them |
| Breakout | Opposite — trades range breakouts instead of range trades |
| Volatility | Overlap — both use Bollinger Bands and ATR |

## Key Lesson

**Mean reversion and trend following are complementary.** A portfolio that
includes both has smoother equity curves — trend following profits in
directional markets, mean reversion profits in range-bound markets.
