"""Pakistan Stock Exchange provider.

PSX does not publish a free documented streaming feed. We support two modes:
  1. A configured live/JSON endpoint (PSX_API_BASE) if the user has access.
  2. Fallback to Yahoo Finance delayed quotes (works out of the box).
"""
from __future__ import annotations

import threading
from typing import Optional

import pandas as pd
import requests

from app.data.base import CandleStore, Quote, utcnow
from app.data.yahoo import yahoo_provider
from config import CONFIG


class PSXProvider:
    def __init__(self) -> None:
        self._base = CONFIG.psx_api_base.rstrip("/")
        self._http = requests.Session()
        self._http.headers.update({"User-Agent": "trading-ai-experts/1.0"})

    def live_available(self) -> bool:
        return bool(self._base)

    def get_quote(self, symbol: str) -> Quote | None:
        """Prefer the configured live endpoint; otherwise Yahoo (delayed)."""
        if self.live_available():
            q = self._live_quote(symbol)
            if q is not None:
                return q
        q = yahoo_provider.get_quote(symbol, "equity")
        if q is not None:
            q.source = "yahoo-psx"
            return q
        return None

    def _live_quote(self, symbol: str) -> Quote | None:
        try:
            r = self._http.get(f"{self._base}/quote/{symbol}", timeout=8)
            r.raise_for_status()
            d = r.json()
            return Quote(
                symbol=symbol,
                price=float(d.get("lastPrice", d.get("close", 0))),
                ts=utcnow(),
                source="psx-live",
                change_1d_pct=float(d.get("changePercent", 0.0)) or None,
                volume_24h=float(d.get("volume", 0)) or None,
                currency="PKR",
            )
        except Exception:
            return None

    def get_candles(
        self, symbol: str, tf: str, limit: int = 500
    ) -> pd.DataFrame:
        frames = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        if self.live_available():
            try:
                r = self._http.get(
                    f"{self._base}/candles/{symbol}", params={"tf": tf, "limit": limit}, timeout=8
                )
                r.raise_for_status()
                rows = [
                    {
                        "open": float(c["open"]),
                        "high": float(c["high"]),
                        "low": float(c["low"]),
                        "close": float(c["close"]),
                        "volume": float(c.get("volume", 0)),
                    }
                    for c in r.json()
                ]
                idx = pd.DatetimeIndex([pd.to_datetime(c["ts"], utc=True) for c in r.json()])
                frames = pd.DataFrame(rows, index=idx)
            except Exception:
                frames = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        if frames.empty:
            return yahoo_provider.get_candles(symbol, "equity", tf, limit)
        return frames


psx_provider = PSXProvider()