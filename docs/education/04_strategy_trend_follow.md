# Wave 0: Trend Following Strategy — Logic Before Code

**Strategy:** Trend Following
**Direction:** Long Only (US Stocks), Long + Short (Metals, Crypto)
**Core Idea:** "The trend is your friend until it bends."

---

## The Hypothesis

Financial markets exhibit **trending behavior** — prices that have been rising
tend to continue rising, and prices that have been falling tend to continue
falling. This is driven by:

1. **Momentum** — buyers pile in as prices rise, sellers pile in as prices fall.
2. **Anchoring** — participants adjust expectations slowly.
3. **Herding** — crowd behavior amplifies trends.
4. **Institutional flows** — large funds accumulate/distribute over time.

## The Rules (US Stocks — `USTrendFollowStrategy`)

### Entry (BUY) — all conditions must be true:

| Rule | Condition | Purpose |
|------|-----------|---------|
| Trend filter | `close > SMA(200)` | Confirms long-term uptrend |
| Momentum | `EMA(21) > EMA(50)` | Confirms intermediate momentum |
| RSI band | `45 ≤ RSI(14) ≤ 75` | Avoids overbought entries |
| Volatility | `ATR% < 6%` | Avoids high-volatility environments |

### Exit (SELL) — any condition triggers:

| Rule | Condition | Purpose |
|------|-----------|---------|
| Overbought | `RSI(14) ≥ 70` | Take profit on overextension |
| Trend break | `close < EMA(50)` | Intermediate trend broken |
| Trailing stop | `close < entry_high × (1 - 8%)` | Protect accumulated profits |

### Why This Works

- SMA(200) is the "institutional trend line" — most fund managers watch it.
- EMA(21/50) crossover catches momentum shifts early.
- RSI filter prevents chasing parabolic moves.
- ATR% filter avoids choppy, high-volatility periods.
- Trailing stop locks in profits without predicting tops.

### Why This Can Fail

- **Sideways markets** — trend following whipsaws in ranges.
- **Gap risk** — overnight gaps can blow through stops.
- **Regime change** — a strategy tuned for trending markets fails in mean-reverting ones.
- **Overfitting** — if parameters are curve-fitted to historical data.

## Relation to Other Strategies

| Strategy | Relationship |
|----------|-------------|
| Mean Reversion | Opposite — buys dips instead of breakouts |
| Momentum Breakout | Overlap — both ride trends, but breakout uses price levels |
| Volatility Breakout | Overlap — both exploit expansion, but different entry logic |

## Key Lesson

**No strategy works everywhere.** Trend following excels in trending markets
but hemorrhages in ranges. This is why we test across multiple regimes and
compare against Buy & Hold.
