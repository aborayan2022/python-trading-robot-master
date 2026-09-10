# Wave 0: Breakout Strategy — Logic Before Code

**Strategy:** Breakout / Momentum Breakout
**Direction:** Long + Short (all markets)
**Core Idea:** "Buy new highs, sell new lows — with confirmation."

---

## The Hypothesis

When price breaks through a well-established support or resistance level,
it signals a **shift in supply/demand balance**. The breakout triggers:
1. **Stop-loss cascades** — trapped traders exit, amplifying the move.
2. **Momentum chasing** — trend followers pile in.
3. **New information** — the breakout reflects fundamental change.

## The Rules

### Entry (BUY — upside breakout):

| Rule | Condition | Purpose |
|------|-----------|---------|
| Price breakout | `close > highest_close(20) + ATR(14)` | Confirmed breakout above range |
| Volume confirmation | `volume > 1.5× avg_volume(20)` | Participation confirms breakout |
| Trend alignment | `close > SMA(100)` | Breakout in direction of trend |

### Entry (SELL SHORT — downside breakout):

| Rule | Condition | Purpose |
|------|-----------|---------|
| Price breakdown | `close < lowest_close(20) - ATR(14)` | Confirmed breakdown below range |
| Volume confirmation | `volume > 1.5× avg_volume(20)` | Selling pressure confirmed |
| Trend alignment | `close < SMA(100)` | Breakdown in direction of trend |

### Exit — trailing stop:

| Rule | Condition | Purpose |
|------|-----------|---------|
| Trailing stop | `close < highest_since_entry × (1 - 2×ATR% trail)` | Protect profits |
| Time stop | `bars_held > 30` | Exit if momentum stalls |
| Reverse breakout | `close crosses back into range` | Breakout failed |

### Why This Works

- Breakouts represent real shifts in market structure.
- Volume confirmation filters out false breakouts (fakeouts).
- Trend alignment prevents counter-trend traps.
- ATR-based stops adapt to each asset's volatility.

### Why This Can Fail

- **Fakeouts** — most breakouts fail (60-70% in ranging markets).
- **Late entry** — by the time breakout is confirmed, much of the move is done.
- **Whipsaws** — volatile markets produce many false breakouts.
- **Gap risk** — overnight gaps can invalidate breakout levels.

## Metals-Specific Breakout Logic

Metals break out during macro regime shifts:
- Gold breaking $2000 → inflation fears intensifying.
- Silver breaking $30 → industrial demand + monetary premium.
- Platinum breaking resistance → supply shortage narrative.

## Crypto-Specific Breakout Logic

Crypto breakouts are amplified by:
- Leverage cascades (futures liquidations).
- Social media momentum (FOMO cycles).
- Exchange listing effects.

## Relation to Other Strategies

| Strategy | Relationship |
|----------|-------------|
| Trend Following | Overlap — both ride momentum, but breakout uses price levels |
| Mean Reversion | Opposite — breakout trades range exits, mean reversion trades range trades |
| Volatility | Overlap — both exploit expansion from compression |

## Key Lesson

**Breakout strategies require strict risk management** because the win rate
is typically 30-40%. The profitability comes from large winners outweighing
many small losers. Position sizing and stop discipline are critical.
