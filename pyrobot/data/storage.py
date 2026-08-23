"""Dataset storage and versioning for quantitative research and reproducibility."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from pyrobot.logging_config import get_logger

logger = get_logger("data_storage")


@dataclass
class DatasetVersion:
    """Metadata describing an immutable dataset snapshot for research reproducibility."""

    dataset_id: str
    symbol: str
    frequency: str
    start_time: datetime
    end_time: datetime
    row_count: int
    checksum: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    file_path: str = ""
    columns: List[str] = field(default_factory=list)
    quality_score: float = 1.0

    def to_dict(self) -> Dict:
        return {
            "dataset_id": self.dataset_id,
            "symbol": self.symbol,
            "frequency": self.frequency,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "row_count": self.row_count,
            "checksum": self.checksum,
            "created_at": self.created_at.isoformat(),
            "file_path": self.file_path,
            "columns": self.columns,
            "quality_score": self.quality_score,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DatasetVersion":
        return cls(
            dataset_id=data["dataset_id"],
            symbol=data["symbol"],
            frequency=data["frequency"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]),
            row_count=data["row_count"],
            checksum=data["checksum"],
            created_at=datetime.fromisoformat(data["created_at"]),
            file_path=data.get("file_path", ""),
            columns=data.get("columns", []),
            quality_score=data.get("quality_score", 1.0),
        )


class DatasetStore:
    """Manages Parquet storage, versioning, and checksum verification of market datasets."""

    def __init__(self, base_dir: Path | str = "data/market") -> None:
        self.base_dir = Path(base_dir)
        self.meta_dir = self.base_dir / "_metadata"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir.mkdir(parents=True, exist_ok=True)

    def _compute_df_checksum(self, df: pd.DataFrame) -> str:
        """Compute deterministic SHA256 checksum across DataFrame contents."""
        clean = df.copy()
        clean.index = pd.to_datetime(clean.index, utc=True).astype("int64") // 10**9
        clean = clean.round(6)
        serialized = clean.to_json(orient="split").encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()

    def save_dataset(
        self,
        df: pd.DataFrame,
        symbol: str,
        frequency: str = "1d",
        quality_score: float = 1.0,
    ) -> DatasetVersion:
        """Save a market dataset to Parquet format with checksum metadata."""
        if df.empty:
            raise ValueError("Cannot save empty DataFrame to DatasetStore")

        # Sort and ensure datetime index is UTC
        clean_df = df.copy()
        if not isinstance(clean_df.index, pd.DatetimeIndex):
            if "datetime" in clean_df.columns:
                clean_df["datetime"] = pd.to_datetime(clean_df["datetime"], utc=True)
                clean_df.set_index("datetime", inplace=True)
            else:
                raise ValueError("DataFrame must have a DatetimeIndex or 'datetime' column")

        clean_df.sort_index(inplace=True)
        start_time = clean_df.index.min().to_pydatetime()
        end_time = clean_df.index.max().to_pydatetime()
        checksum = self._compute_df_checksum(clean_df)

        date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dataset_id = f"{symbol.upper()}_{frequency}_{date_str}_{checksum[:8]}"

        # Try parquet first; fallback to compressed csv.gz if pyarrow not installed
        file_format = "parquet"
        try:
            filename = f"{dataset_id}.parquet"
            file_path = self.base_dir / filename
            clean_df.to_parquet(file_path, compression="snappy")
        except (ImportError, ValueError):
            file_format = "csv_gz"
            filename = f"{dataset_id}.csv.gz"
            file_path = self.base_dir / filename
            clean_df.to_csv(file_path, compression="gzip")

        version = DatasetVersion(
            dataset_id=dataset_id,
            symbol=symbol.upper(),
            frequency=frequency,
            start_time=start_time,
            end_time=end_time,
            row_count=len(clean_df),
            checksum=checksum,
            file_path=str(file_path),
            columns=list(clean_df.columns),
            quality_score=quality_score,
        )

        # Save metadata JSON
        meta_file = self.meta_dir / f"{dataset_id}.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(version.to_dict(), f, indent=2)

        logger.info(
            "Saved dataset %s (format=%s, rows=%d, checksum=%s)",
            dataset_id,
            file_format,
            len(clean_df),
            checksum[:8],
        )
        return version

    def load_dataset(self, dataset_id: str) -> tuple[pd.DataFrame, DatasetVersion]:
        """Load a dataset by ID and verify its cryptographic checksum."""
        meta_file = self.meta_dir / f"{dataset_id}.json"
        if not meta_file.exists():
            raise FileNotFoundError(f"Metadata for dataset {dataset_id} not found")

        with open(meta_file, "r", encoding="utf-8") as f:
            version = DatasetVersion.from_dict(json.load(f))

        file_path = Path(version.file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Dataset file {file_path} not found")

        if file_path.name.endswith(".parquet"):
            df = pd.read_parquet(file_path)
        else:
            df = pd.read_csv(file_path, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True)

        current_checksum = self._compute_df_checksum(df)
        if current_checksum != version.checksum:
            raise ValueError(
                f"Checksum mismatch for dataset {dataset_id}! "
                f"Expected {version.checksum}, got {current_checksum}. Data corrupted!"
            )

        return df, version

    def list_versions(self, symbol: Optional[str] = None) -> List[DatasetVersion]:
        """List all available dataset versions."""
        versions = []
        for meta_path in self.meta_dir.glob("*.json"):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    v = DatasetVersion.from_dict(json.load(f))
                    if symbol is None or v.symbol == symbol.upper():
                        versions.append(v)
            except Exception as e:
                logger.warning("Failed to load metadata %s: %s", meta_path, e)

        return sorted(versions, key=lambda x: x.created_at, reverse=True)
