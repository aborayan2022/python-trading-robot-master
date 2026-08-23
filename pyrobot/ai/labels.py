"""Label construction for supervised learning on price data.

Lookahead contract: labels USE future data by definition (forward returns),
but they are aligned so that the label at time t is built exclusively from
bars t+1 .. t+h. Pair features at time t with the label at time t, then drop
the trailing `horizon` unlabeled rows before training — drop_unlabeled() does
that. Features themselves must remain strictly backward-looking (see
pyrobot/features/).
"""

from typing import Sequence

import numpy as np
import pandas as pd


class LabelBuilder:
    """Builds forward-looking training targets from OHLCV data."""

    @staticmethod
    def _grouped(frame: pd.DataFrame, column: str) -> pd.Series | pd.Series:
        """Return the column as a Series, grouped per symbol when MultiIndex."""
        if isinstance(frame.index, pd.MultiIndex):
            return frame[column].groupby(level=0)
        return frame[column]

    @staticmethod
    def forward_returns(
        df: pd.DataFrame,
        horizons: Sequence[int] = (1, 5, 10, 21),
    ) -> pd.DataFrame:
        """Forward returns over multiple horizons: close.shift(-h)/close - 1.

        Args:
            df: OHLCV frame with a 'close' column, indexed by timestamp or by
                (symbol, timestamp) — grouped per symbol when MultiIndex.
            horizons: Forward bar counts.

        Returns:
            DataFrame with columns fwd_ret_{h}; the trailing h rows per symbol
            are NaN (unknown future) and must be dropped before training.
        """
        out = pd.DataFrame(index=df.index)
        for h in horizons:
            if h <= 0:
                raise ValueError(f"Horizons must be positive, got {h}")
            if isinstance(df.index, pd.MultiIndex):
                grouped = df["close"].groupby(level=0)
                out[f"fwd_ret_{h}"] = grouped.transform(
                    lambda s: s.shift(-h) / s - 1.0
                )
            else:
                out[f"fwd_ret_{h}"] = df["close"].shift(-h) / df["close"] - 1.0
        return out

    def direction_labels(
        self,
        df: pd.DataFrame,
        horizon: int = 1,
        threshold: float = 0.0,
    ) -> pd.Series:
        """Binary direction label: 1 if forward return > threshold else 0.

        Rows whose future is unknown (trailing `horizon` rows per symbol) are
        NaN — drop them with drop_unlabeled() before fitting a model.
        """
        fwd = self.forward_returns(df, horizons=(horizon,))[f"fwd_ret_{horizon}"]
        labels = (fwd > threshold).astype(float)
        labels[fwd.isna()] = np.nan
        labels.name = f"dir_{horizon}"
        return labels

    def triple_barrier_labels(
        self,
        df: pd.DataFrame,
        horizon: int = 10,
        up_mult: float = 2.0,
        down_mult: float = 1.0,
        atr_period: int = 14,
    ) -> pd.Series:
        """López de Prado triple-barrier labels: +1 (profit), -1 (stop), 0 (timeout).

        For each bar t (with at least atr_period of history for ATR at entry,
        computed from PAST bars only), walks bars t+1..t+horizon:
          - long profit barrier: entry + up_mult * ATR_t   -> +1
          - long stop barrier:   entry - down_mult * ATR_t -> -1
          - neither touched within horizon                 -> 0
        When a bar's high/low straddles both barriers, the STOP is assumed to
        hit first (conservative). Rows without enough history or future are NaN.
        """
        if isinstance(df.index, pd.MultiIndex):
            pieces = []
            for symbol, g in df.groupby(level=0):
                piece = self._triple_barrier_single(g, horizon, up_mult, down_mult, atr_period)
                pieces.append(piece)
            out = pd.concat(pieces)
            return out.sort_index() if not out.index.is_monotonic_decreasing else out

        return self._triple_barrier_single(df, horizon, up_mult, down_mult, atr_period)

    def _triple_barrier_single(
        self,
        g: pd.DataFrame,
        horizon: int,
        up_mult: float,
        down_mult: float,
        atr_period: int,
    ) -> pd.Series:
        high = g["high"].to_numpy(dtype=float)
        low = g["low"].to_numpy(dtype=float)
        close = g["close"].to_numpy(dtype=float)
        open_ = g["open"].to_numpy(dtype=float) if "open" in g else close

        prev_close = np.roll(close, 1)
        prev_close[0] = np.nan
        tr = np.maximum.reduce([
            high - low,
            np.abs(high - prev_close),
            np.abs(low - prev_close),
        ])
        # Rolling ATR from PAST bars only (inclusive mean of the window ending at t).
        atr = pd.Series(tr).rolling(atr_period, min_periods=atr_period).mean().to_numpy()

        n = len(g)
        labels = np.full(n, np.nan)
        for t in range(n):
            if np.isnan(atr[t]) or atr[t] <= 0:
                continue
            entry = close[t]
            upper = entry + up_mult * atr[t]
            lower = entry - down_mult * atr[t]
            outcome = None
            for j in range(t + 1, min(t + 1 + horizon, n)):
                stop_first = low[j] <= lower
                profit = high[j] >= upper
                if stop_first:
                    outcome = -1.0  # conservative: stop wins ties
                    break
                if profit:
                    outcome = 1.0
                    break
            if outcome is None:
                if t + 1 + horizon <= n:  # full window observed, neither barrier hit
                    outcome = 0.0
            labels[t] = outcome

        out = pd.Series(labels, index=g.index, name=f"tb_{horizon}")
        _ = open_  # reserved for entry-at-next-open variants
        return out

    @staticmethod
    def drop_unlabeled(labels: pd.Series, features: pd.DataFrame | None = None):
        """Drop NaN label rows; optionally align features to the same rows.

        Returns:
            (labels_dropped, features_dropped) when features given, else labels_dropped.
        """
        mask = labels.notna()
        if features is None:
            return labels[mask]
        return labels[mask], features.loc[mask]
