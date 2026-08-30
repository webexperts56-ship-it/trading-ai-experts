"""Binance provider: real-time crypto via REST + websocket streams.

Free, no API key. Geo-blocked regions can override the base URLs in .env
(e.g. Binance.US). If the websocket can't connect we fall back to polling REST.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests

from app.data.base import CandleStore, Quote, utcnow
from config import CONFIG

BINANCE_TFS = ["1m", "5m", "15m", "1h", "4h", "1d"]


def binance_symbol(symbol: str) -> str:
    base = symbol.upper()
    return f"{base}USDT"


def _to_ts(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


class BinanceProvider:
    def __init__(self) -> None:
        self._base = CONFIG.binance_rest_url.rstrip("/")
        self._http = requests.Session()
        self._http.headers.update({"User-Agent": "trading-ai-experts/1.0"})
        self._ws_events: list[bytes] = []
        self._threads: list[threading.Thread] = []
        self._near_price: dict[str, float] = {}
        self._near_lock = threading.Lock()

    # ------------------------------------------------------------------ REST
    def klines(self, symbol: str, tf: str, limit: int = 500) -> pd.DataFrame:
        sym = binance_symbol(symbol)
        url = f"{self._base}/api/v3/klines"
        params = {"symbol": sym, "interval": tf, "limit": limit}
        try:
            r = self._http.get(url, params=params, timeout=10)
            r.raise_for_status()
            rows = []
            for k in r.json():
                rows.append(
                    {
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5]),
                    }
                )
            idx = pd.DatetimeIndex([_to_ts(k[0]) for k in r.json()], name="ts")
            return pd.DataFrame(rows, index=idx)
        except Exception:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def get_quote(self, symbol: str) -> Quote | None:
        sym = binance_symbol(symbol)
        url = f"{self._base}/api/v3/ticker/24hr"
        try:
            r = self._http.get(url, params={"symbol": sym}, timeout=10)
            r.raise_for_status()
            d = r.json()
            return Quote(
                symbol=symbol,
                price=float(d.get("lastPrice", 0.0)) or None,
                ts=utcnow(),
                source="binance",
                change_1d_pct=float(d.get("priceChangePercent", 0.0)),
                change_1h_pct=None,
                volume_24h=float(d.get("quoteVolume", 0.0)),
                currency="USD",
            )
        except Exception:
            return None

    # -------------------------------------------------------------------- WS
    def start_ws(self, symbols: list[str], store: CandleStore) -> None:
        """Start the minutely websocket feed for a set of crypto symbols."""
        t = threading.Thread(
            target=self._ws_loop, args=(symbols, store), daemon=True, name=f"binance-ws"
        )
        t.start()
        self._threads.append(t)

    def _ws_loop(self, symbols: list[str], store: CandleStore) -> None:
        import websockets

        while True:
            if not self._ws_once(symbols, store, websockets):
                time.sleep(5)

    def _ws_once(self, symbols: list[str], store: CandleStore, websockets) -> bool:
        streams = []
        for s in symbols:
            sym = binance_symbol(s).lower()
            for tf in BINANCE_TFS:
                streams.append(f"{sym}@kline_{tf}")
        url = f"{CONFIG.binance_ws_url}/stream?streams={'/'.join(streams)}"
        try:
            with websockets.connect(url, ping_interval=20, ping_timeout=20, open_timeout=10) as ws:
                while True:
                    msg = json.loads(ws.recv())
                    if not isinstance(msg, dict) or "stream" not in msg:
                        continue
                    data = msg["data"]
                    k = data.get("k", {})
                    sym = k.get("s", "").replace("USDT", "").upper()
                    if not sym:
                        continue
                    tf = k.get("i", "")
                    ts = datetime.fromtimestamp(k["t"] / 1000.0, tz=timezone.utc)
                    row = {
                        "ts": ts,
                        "open": float(k["o"]),
                        "high": float(k["h"]),
                        "low": float(k["l"]),
                        "close": float(k["c"]),
                        "volume": float(k["v"]),
                    }
                    store.update(tf, row)
                    with self._near_lock:
                        self._near_price[sym] = float(k["c"])
        except Exception:
            return False

    def near_price(self, symbol: str) -> Optional[float]:
        with self._near_lock:
            return self._near_price.get(symbol.upper())


binance_provider = BinanceProvider()