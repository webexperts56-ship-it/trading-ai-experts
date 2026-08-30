"""Canonical snapshot schema shared by the engine, web dashboard, alerts and store.

A Snapshot is the complete evaluation of one ticker at one point in time:
quote + fundamentals + technicals + trend + a directional signal for each
forecast horizon. Everything downstream (dashboard, persistence, alerting,
backtesting) consumes the dict form produced by Snapshot.to_dict().
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import os

# forecast horizons: key -> label / seconds
HORIZONS: dict[str, dict] = {
    "1MIN": {"label": "1 min", "seconds": 60},
    "5MIN": {"label": "5 min", "seconds": 300},
    "1H": {"label": "1 hour", "seconds": 3600},
    "6H": {"label": "6 hours", "seconds": 21600},
    "1D": {"label": "1 day", "seconds": 86400},
}
HORIZON_ORDER: list[str] = ["1MIN", "5MIN", "1H", "6H", "1D"]
TO_SECONDS = {k: v["seconds"] for k, v in HORIZONS.items()}

ACTIONS = ["STRONG_SELL", "SELL", "NEUTRAL", "BUY", "STRONG_BUY"]


def _signal_threshold() -> float:
    try:
        return float(os.getenv("SIGNAL_THRESHOLD", "5"))
    except (TypeError, ValueError):
        return 5.0


def action_for_score(score: float) -> str:
    th = _signal_threshold()
    strong = th * 12
    if score >= strong:
        return "STRONG_BUY"
    if score >= th:
        return "BUY"
    if score <= -strong:
        return "STRONG_SELL"
    if score <= -th:
        return "SELL"
    return "NEUTRAL"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class HorizonSignal:
    horizon: str
    seconds: int
    score: float
    action: str
    probability_up: float
    confidence: float
    drivers: dict = field(default_factory=dict)
    ml_probability: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    resolved_actual: Optional[float] = None
    resolved_correct: Optional[bool] = None
    resolved_ts: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "horizon": self.horizon,
            "label": HORIZONS.get(self.horizon, {}).get("label", self.horizon),
            "seconds": self.seconds,
            "score": round(self.score, 1),
            "action": self.action,
            "probability_up": round(self.probability_up, 4),
            "confidence": round(self.confidence, 1),
            "drivers": {k: round(v, 1) for k, v in self.drivers.items()},
            "ml_probability": round(self.ml_probability, 4) if self.ml_probability is not None else None,
            "take_profit": self.take_profit,
            "stop_loss": self.stop_loss,
            "resolved_actual": self.resolved_actual,
            "resolved_correct": self.resolved_correct,
            "resolved_ts": self.resolved_ts,
        }


@dataclass
class Snapshot:
    symbol: str
    name: str
    asset_class: str
    market: str
    provider: str
    ts: str
    quote: dict = field(default_factory=dict)
    fundamental: dict = field(default_factory=dict)
    technical: dict = field(default_factory=dict)
    trend: dict = field(default_factory=dict)
    signals: list[HorizonSignal] = field(default_factory=list)
    composite: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "asset_class": self.asset_class,
            "market": self.market,
            "provider": self.provider,
            "ts": self.ts,
            "quote": self.quote,
            "fundamental": self.fundamental,
            "technical": self.technical,
            "trend": self.trend,
            "signals": [s.to_dict() for s in self.signals],
            "composite": self.composite,
            "meta": self.meta,
        }


class SharedState:
    """Thread-safe holder of the latest analysis snapshots and alerts.

    The RT engine writes here; the web server and alert monitor read from it.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshots: dict[str, dict] = {}
        self._alerts: list[dict] = []
        self._market_ctx: dict = {}
        self._started_ts = time.time()

    def put_snapshot(self, snap: dict) -> None:
        with self._lock:
            self._snapshots[snap["symbol"]] = snap

    def get_snapshot(self, symbol: str) -> Optional[dict]:
        with self._lock:
            return self._snapshots.get(symbol)

    def all_snapshots(self) -> list[dict]:
        with self._lock:
            return list(self._snapshots.values())

    def add_alert(self, alert: dict) -> None:
        alert["ts"] = alert.get("ts") or utcnow().isoformat()
        with self._lock:
            self._alerts.insert(0, alert)
            del self._alerts[200:]

    def recent_alerts(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return self._alerts[:limit]

    def set_market_ctx(self, ctx: dict) -> None:
        with self._lock:
            self._market_ctx = ctx

    def get_market_ctx(self) -> dict:
        with self._lock:
            return self._market_ctx