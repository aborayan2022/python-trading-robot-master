"""Data Quality Engine for validating incoming market data.

Checks for missing values, price anomalies, time gaps, duplicates,
out-of-order timestamps, and staleness.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pandas as pd

from pyrobot.exceptions import DataQualityError
from pyrobot.logging_config import get_logger

logger = get_logger("data_quality")

_PRICE_JUMP_THRESHOLD = 0.50
_STALENESS_THRESHOLD = timedelta(minutes=5)


@dataclass
class DataAnomaly:
    """Single anomaly record detected during validation."""

    anomaly_type: str
    severity: str
    symbol: str
    timestamp: datetime
    detail: str

    def __str__(self) -> str:
        return (
            f"[{self.severity.upper()}] {self.anomaly_type} | "
            f"{self.symbol} @ {self.timestamp} — {self.detail}"
        )


@dataclass
class DataQualityReport:
    """Result of a data quality validation pass."""

    is_valid: bool
    anomalies: List[DataAnomaly] = field(default_factory=list)
    total_records: int = 0
    valid_records: int = 0

    @property
    def quality_score(self) -> float:
        if self.total_records == 0:
            return 0.0
        return self.valid_records / self.total_records

    def summary(self) -> str:
        lines = [
            "── Data Quality Report ──",
            f"  Valid:       {self.is_valid}",
            f"  Records:     {self.total_records}",
            f"  Valid recs:  {self.valid_records}",
            f"  Score:       {self.quality_score:.2%}",
        ]
        if self.anomalies:
            counts: dict[str, int] = {}
            for a in self.anomalies:
                counts[a.anomaly_type] = counts.get(a.anomaly_type, 0) + 1
            lines.append(f"  Anomalies:   {len(self.anomalies)}")
            for atype, count in counts.items():
                lines.append(f"    {atype}: {count}")
        else:
            lines.append("  Anomalies:   0")
        lines.append("─────────────────────────")
        return "\n".join(lines)


@dataclass
class DatasetMetadata:
    """Tracks dataset-level statistics."""

    symbol: str
    start_date: datetime
    end_date: datetime
    bar_count: int
    missing_count: int
    quality_score: float
    coverage_pct: float


class DataQualityEngine:
    """Validates incoming market data for common quality issues."""

    def __init__(
        self,
        stale_threshold: timedelta = _STALENESS_THRESHOLD,
        price_jump_pct: float = _PRICE_JUMP_THRESHOLD,
        expected_interval: Optional[timedelta] = None,
    ) -> None:
        self.stale_threshold = stale_threshold
        self.price_jump_pct = price_jump_pct
        self.expected_interval = expected_interval

    # ── Public API ────────────────────────────────────────────────────────

    def validate_candles(self, candles: List[dict]) -> DataQualityReport:
        if not candles:
            return DataQualityReport(is_valid=False, total_records=0, valid_records=0)

        df = pd.DataFrame(candles)
        anomalies = self.check_anomalies(df)

        critical = sum(1 for a in anomalies if a.severity == "critical")
        is_valid = critical == 0 and self._score(anomalies, len(df)) > 0.0

        report = DataQualityReport(
            is_valid=is_valid,
            anomalies=anomalies,
            total_records=len(df),
            valid_records=len(df) - critical,
        )

        if not report.is_valid:
            logger.warning("Candle validation failed: %s", report.summary())
        else:
            logger.info("Candle validation passed: %s", report.summary())

        return report

    def validate_quotes(self, quotes: List[dict]) -> DataQualityReport:
        if not quotes:
            return DataQualityReport(is_valid=False, total_records=0, valid_records=0)

        df = pd.DataFrame(quotes)
        anomalies: List[DataAnomaly] = []

        if "symbol" in df.columns and "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

            for symbol, group in df.groupby("symbol"):
                self._check_duplicates(group, symbol, anomalies)
                self._check_ordering(group, symbol, anomalies)
                self._check_staleness(group, symbol, anomalies)

        critical = sum(1 for a in anomalies if a.severity == "critical")
        is_valid = critical == 0

        report = DataQualityReport(
            is_valid=is_valid,
            anomalies=anomalies,
            total_records=len(df),
            valid_records=len(df) - critical,
        )

        if not report.is_valid:
            logger.warning("Quote validation failed: %s", report.summary())
        else:
            logger.info("Quote validation passed: %s", report.summary())

        return report

    def check_anomalies(self, df: pd.DataFrame) -> List[DataAnomaly]:
        anomalies: List[DataAnomaly] = []

        if df.empty:
            return anomalies

        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

        symbol = df["symbol"].iloc[0] if "symbol" in df.columns else "UNKNOWN"

        self._check_missing_values(df, symbol, anomalies)
        self._check_price_anomalies(df, symbol, anomalies)

        if "timestamp" in df.columns:
            self._check_duplicates(df, symbol, anomalies)
            self._check_ordering(df, symbol, anomalies)
            self._check_time_gaps(df, symbol, anomalies)
            self._check_staleness(df, symbol, anomalies)

        return anomalies

    def compute_metadata(
        self, candles: List[dict], frequency: timedelta = timedelta(days=1)
    ) -> DatasetMetadata:
        if not candles:
            raise DataQualityError("Cannot compute metadata for empty dataset")

        df = pd.DataFrame(candles)
        symbol = df["symbol"].iloc[0] if "symbol" in df.columns else "UNKNOWN"

        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df.dropna(subset=["timestamp"], inplace=True)
        df.sort_values("timestamp", inplace=True)

        start = df["timestamp"].min()
        end = df["timestamp"].max()

        expected_bars = max(1, int((end - start) / frequency) + 1)
        actual_bars = len(df)

        missing = df.isnull().any(axis=1).sum()
        anomalies = self.check_anomalies(df)
        critical = sum(1 for a in anomalies if a.severity == "critical")

        valid = actual_bars - critical
        quality = valid / actual_bars if actual_bars else 0.0
        coverage = actual_bars / expected_bars if expected_bars else 0.0

        return DatasetMetadata(
            symbol=symbol,
            start_date=start,
            end_date=end,
            bar_count=actual_bars,
            missing_count=int(missing),
            quality_score=quality,
            coverage_pct=min(1.0, coverage),
        )

    # ── Internal checks ───────────────────────────────────────────────────

    def _check_missing_values(
        self, df: pd.DataFrame, symbol: str, anomalies: List[DataAnomaly]
    ) -> None:
        price_cols = [c for c in ("open", "high", "low", "close") if c in df.columns]
        if not price_cols:
            return

        for col in price_cols:
            mask = df[col].isna() | (df[col] == 0)
            for idx in df.index[mask]:
                ts = self._get_timestamp(df, idx)
                severity = "critical" if col in ("close", "open") else "warning"
                anomalies.append(
                    DataAnomaly(
                        anomaly_type="missing_value",
                        severity=severity,
                        symbol=symbol,
                        timestamp=ts,
                        detail=f"{col} is null or zero at index {idx}",
                    )
                )

        if "volume" in df.columns:
            mask = df["volume"].isna()
            for idx in df.index[mask]:
                anomalies.append(
                    DataAnomaly(
                        anomaly_type="missing_value",
                        severity="warning",
                        symbol=symbol,
                        timestamp=self._get_timestamp(df, idx),
                        detail=f"volume is null at index {idx}",
                    )
                )

    def _check_price_anomalies(
        self, df: pd.DataFrame, symbol: str, anomalies: List[DataAnomaly]
    ) -> None:
        if "volume" in df.columns:
            zero_vol = df.index[df["volume"] == 0]
            for idx in zero_vol:
                anomalies.append(
                    DataAnomaly(
                        anomaly_type="price_jump",
                        severity="info",
                        symbol=symbol,
                        timestamp=self._get_timestamp(df, idx),
                        detail="zero volume detected",
                    )
                )

        close_col = "close" if "close" in df.columns else None
        if close_col is None:
            return

        prices = df[close_col].astype(float)
        pct = prices.pct_change()

        jumps = pct.index[pct.abs() > self.price_jump_pct]
        for idx in jumps:
            change = pct[idx]
            anomalies.append(
                DataAnomaly(
                    anomaly_type="price_jump",
                    severity="critical" if abs(change) > 2 * self.price_jump_pct else "warning",
                    symbol=symbol,
                    timestamp=self._get_timestamp(df, idx),
                    detail=f"price changed {change:+.2%} from previous bar",
                )
            )

    def _check_duplicates(
        self, df: pd.DataFrame, symbol: str, anomalies: List[DataAnomaly]
    ) -> None:
        if "timestamp" not in df.columns:
            return

        dups = df[df.duplicated(subset=["timestamp"], keep=False)]
        seen: set = set()
        for _, row in dups.iterrows():
            ts = row["timestamp"]
            if pd.isna(ts) or ts in seen:
                continue
            seen.add(ts)
            count = (df["timestamp"] == ts).sum()
            anomalies.append(
                DataAnomaly(
                    anomaly_type="duplicate",
                    severity="warning",
                    symbol=symbol,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    detail=f"{count} records share timestamp {ts}",
                )
            )

    def _check_ordering(
        self, df: pd.DataFrame, symbol: str, anomalies: List[DataAnomaly]
    ) -> None:
        if "timestamp" not in df.columns or len(df) < 2:
            return

        ts = df["timestamp"]
        mask = ts < ts.shift(1)
        for idx in df.index[mask]:
            anomalies.append(
                DataAnomaly(
                    anomaly_type="out_of_order",
                    severity="critical",
                    symbol=symbol,
                    timestamp=self._get_timestamp(df, idx),
                    detail="timestamp is before previous row",
                )
            )

    def _check_time_gaps(
        self, df: pd.DataFrame, symbol: str, anomalies: List[DataAnomaly]
    ) -> None:
        if len(df) < 2 or "timestamp" not in df.columns:
            return

        interval = self.expected_interval
        if interval is None:
            diffs = df["timestamp"].diff().dropna()
            if diffs.empty:
                return
            interval = diffs.mode().iloc[0] if not diffs.mode().empty else diffs.median()

        ts = df["timestamp"]
        diffs = ts.diff()
        gap_mask = diffs > interval * 1.5

        for idx in df.index[gap_mask]:
            prev_idx = df.index.get_loc(idx)
            if prev_idx == 0:
                continue
            prev_ts = ts.iloc[prev_idx - 1]
            curr_ts = ts.iloc[prev_idx]
            anomalies.append(
                DataAnomaly(
                    anomaly_type="gap",
                    severity="warning",
                    symbol=symbol,
                    timestamp=self._get_timestamp(df, idx),
                    detail=f"gap of {curr_ts - prev_ts} (expected ~{interval})",
                )
            )

    def _check_staleness(
        self, df: pd.DataFrame, symbol: str, anomalies: List[DataAnomaly]
    ) -> None:
        if "timestamp" not in df.columns or df["timestamp"].dropna().empty:
            return

        now = datetime.now(timezone.utc)
        latest = df["timestamp"].max()
        if pd.isna(latest):
            return

        age = now - latest
        if age > self.stale_threshold:
            anomalies.append(
                DataAnomaly(
                    anomaly_type="stale",
                    severity="critical",
                    symbol=symbol,
                    timestamp=latest.to_pydatetime() if hasattr(latest, "to_pydatetime") else latest,
                    detail=f"data is {age} old (threshold: {self.stale_threshold})",
                )
            )

    @staticmethod
    def _get_timestamp(df: pd.DataFrame, idx) -> datetime:
        ts = df.loc[idx, "timestamp"] if "timestamp" in df.columns else datetime.now(timezone.utc)
        if pd.isna(ts):
            return datetime.now(timezone.utc)
        if hasattr(ts, "to_pydatetime"):
            return ts.to_pydatetime()
        return ts

    @staticmethod
    def _score(anomalies: List[DataAnomaly], total: int) -> float:
        if total == 0:
            return 0.0
        critical = sum(1 for a in anomalies if a.severity == "critical")
        return (total - critical) / total
