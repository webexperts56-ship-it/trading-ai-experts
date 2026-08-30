"""Shared schemas and in-memory candle storage for the data layer."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

import pandas as pd

TIME_FRAMES: list[str] = ["1m", "5m", "15m", "1h", "4h", "1d"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Quote:
    symbol: str
    price: float
    ts: datetime
    source: str
    change_1d_pct: Optional[float] = None
    change_1h_pct: Optional[float] = None
    volume_24h: Optional[float] = None
    market_cap: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    currency: str = "USD"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "ts": self.ts.isoformat(),
            "source": self.source,
            "change_1d_pct": self.change_1d_pct,
            "change_1h_pct": self.change_1h_pct,
            "volume_24h": self.volume_24h,
            "market_cap": self.market_cap,
            "bid": self.bid,
            "ask": self.ask,
            "currency": self.currency,
        }


@dataclass
class FundamentalData:
    symbol: str
    metrics: dict = field(default_factory=dict)  # raw ratios / raw values
    health_score: float = 0.0           # -100..100 financial health
    valuation_score: float = 0.0        # -100..100 valuation attractiveness
    fundamental_score: float = 0.0      # combined -100..100
    details: dict = field(default_factory=dict)
    fetched_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "health_score": self.health_score,
            "valuation_score": self.valuation_score,
            "fundamental_score": self.fundamental_score,
            "details": self.details,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


class CandleStore:
    """Thread-safe, in-memory storage of OHLCV candles per timeframe.

    Each timeframe holds a pandas DataFrame indexed by UTC timestamps with
    columns: open, high, low, close, volume.
    """

    def __init__(self, symbol: str, tf_list: list[str] | None = None):
        self.symbol = symbol
        self._lock = threading.RLock()
        self._frames: dict[str, pd.DataFrame] = {}
        for tf in tf_list or TIME_FRAMES:
            self._frames[tf] = pd.DataFrame(
                columns=["open", "high", "low", "close", "volume"], dtype=float
            )

    @property
    def timeframes(self) -> list[str]:
        with self._lock:
            return list(self._frames.keys())

    def set_frame(self, tf: str, df: pd.DataFrame) -> None:
        if df is None or df.empty:
            return
        with self._lock:
            clean = df[["open", "high", "low", "close", "volume"]].copy()
            clean.index = pd.to_datetime(clean.index, utc=True)
            clean = clean[~clean.index.duplicated(keep="last")].sort_index()
            existing = self._frames.get(tf, pd.DataFrame(columns=clean.columns))
            if existing.empty:
                self._frames[tf] = clean.dropna()
                return
            merged = pd.concat([existing, clean])
            self._frames[tf] = merged[~merged.index.duplicated(keep="last")].sort_index().dropna()

    def update(self, tf: str, row: dict) -> None:
        """Update or insert a single candle row."""
        with self._lock:
            df = self._frames.setdefault(
                tf, pd.DataFrame(columns=["open", "high", "low", "close", "volume"], dtype=float)
            )
            ts = pd.to_datetime(row["ts"], utc=True)
            idx = pd.DatetimeIndex([ts])
            newrow = pd.DataFrame(
                [{
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }],
                index=idx,
            )
            if ts in df.index:
                df.loc[ts] = newrow.iloc[0]
            elif not df.empty:
                df = pd.concat([df, newrow]).sort_index()
            else:
                df = newrow.sort_index()
            self._frames[tf] = df

    def get(self, tf: str, limit: int | None = None) -> pd.DataFrame:
        with self._lock:
            df = self._frames.get(tf)
            if df is None or df.empty:
                return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
            return df.tail(limit) if limit else df.copy()

    def latest(self, tf: str) -> dict | None:
        df = self.get(tf)
        if df.empty:
            return None
        last = df.iloc[-1]
        return {
            "ts": df.index[-1],
            "open": float(last["open"]),
            "high": float(last["high"]),
            "low": float(last["low"]),
            "close": float(last["close"]),
            "volume": float(last["volume"]),
        }

    def close_series(self, tf: str, limit: int | None = None) -> pd.Series:
        df = self.get(tf, limit)
        if df.empty:
            return pd.Series(dtype=float)
        return df["close"]