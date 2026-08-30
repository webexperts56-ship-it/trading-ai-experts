"""Yahoo Finance provider: quotes, candle history and fundamentals.

Used for PSX equities (Karachi-suffix symbols) and as a fallback source for
crypto. Quotes via Yahoo are delayed; for real-time crypto we layer Binance on
top, and the PSX provider attempts a live feed when configured.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from app.data.base import CandleStore, FundamentalData, Quote, utcnow
from app.data.cache import TTLCache
from config import CONFIG

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

YH_CRYPTO = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "BNB": "BNB-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
    "ADA": "ADA-USD",
    "AVAX": "AVAX-USD",
    "LINK": "LINK-USD",
    "MATIC": "MATIC-USD",
    "DOT": "DOT-USD",
    "LTC": "LTC-USD",
    "SAND": "SAND-USD",
    "UNI": "UNI-USD",
}


def to_yahoo_symbol(symbol: str, asset_class: str) -> str:
    if asset_class == "crypto":
        return YH_CRYPTO.get(symbol.upper(), f"{symbol.upper()}-USD")
    return symbol  # PSX symbols already carry the .KA / .KAR suffix


class YahooProvider:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache = TTLCache(CONFIG.cache_ttl * 4)
        self._fund_cache = TTLCache(3600)

    def available(self) -> bool:
        return yf is not None

    # ------------------------------------------------------------------ quotes
    def get_quote(self, symbol: str, asset_class: str = "equity") -> Quote | None:
        if not self.available():
            return None
        ysym = to_yahoo_symbol(symbol, asset_class)
        key = f"quote:{ysym}"

        def producer() -> Quote | None:
            try:
                t = yf.Ticker(ysym)
                fast = t.fast_info
                price = float(fast["last_price"])
            except Exception:
                try:
                    info = t.info
                    if not info or not info.get("regularMarketPrice"):
                        return None
                    price = float(info["regularMarketPrice"])
                except Exception:
                    return None

            change_1d: Optional[float] = None
            change_1h: Optional[float] = None
            try:
                change_1d = float(fast.get("last_price")) / float(fast.get("open")) - 1
            except Exception:
                pass
            try:
                change_1h = None
            except Exception:
                pass
            return Quote(
                symbol=symbol,
                price=price,
                ts=utcnow(),
                source="yahoo",
                change_1d_pct=round(change_1d * 100, 3) if change_1d is not None else None,
                volume_24h=self._try_float(fast, "last_volume"),
                currency="PKR" if asset_class == "equity" else "USD",
            )

        return self._cache.get_or_call(key, producer)  # type: ignore[return-value]

    @staticmethod
    def _try_float(obj, attr: str) -> Optional[float]:
        try:
            v = float(obj[attr])
            return v if v == v else None  # NaN check
        except Exception:
            return None

    # ------------------------------------------------------------- candles
    def get_candles(
        self,
        symbol: str,
        asset_class: str,
        tf: str,
        limit: int = 500,
    ) -> pd.DataFrame:
        if not self.available():
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        ysym = to_yahoo_symbol(symbol, asset_class)
        key = f"candles:{ysym}:{tf}:{limit}"

        def producer() -> pd.DataFrame:
            try:
                t = yf.Ticker(ysym)
                period = self._period_for(tf, limit)
                df = t.history(period=period, interval=tf, auto_adjust=False)
                if df is None or df.empty:
                    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
                df = df.rename(
                    columns={
                        "Open": "open",
                        "High": "high",
                        "Low": "low",
                        "Close": "close",
                        "Volume": "volume",
                    }
                )
                out = df[["open", "high", "low", "close", "volume"]].tail(limit)
                return out
            except Exception:
                return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        res = self._cache.get_or_call(key, producer)
        if isinstance(res, pd.DataFrame):
            return res.tail(limit)
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    @staticmethod
    def _period_for(tf: str, limit: int) -> str:
        # yfinance rejects very short periods; use generous windows and tail().
        m = {
            "1m": "7d",
            "5m": "60d",
            "15m": "60d",
            "1h": "730d",
            "4h": "730d",
            "1d": "730d",
        }
        return m.get(tf, "60d")

    # --------------------------------------------------------- fundamentals
    def get_fundamentals(self, symbol: str, asset_class: str) -> FundamentalData | None:
        if not self.available() or asset_class != "equity":
            return None
        ysym = to_yahoo_symbol(symbol, asset_class)
        key = f"fund:{ysym}"

        def producer() -> FundamentalData:
            try:
                t = yf.Ticker(ysym)
                info = t.info or {}
                stmts = {}
                try:
                    is_ = t.income_stmt
                    bs_ = t.balance_sheet
                    cf_ = t.cashflow
                    stmts = {"income": is_, "balance": bs_, "cashflow": cf_}
                except Exception:
                    stmts = {}
                fd = FundamentalData(symbol=symbol, fetched_at=utcnow())
                fd.metrics = self._extract_metrics(info)
                fd.details = {"info_keys": len(info), "has_statements": bool(stmts)}
                return fd
            except Exception:
                return FundamentalData(symbol=symbol, fetched_at=utcnow())

        fd = self._fund_cache.get_or_call(key, producer)
        if isinstance(fd, FundamentalData):
            return fd
        return None

    @staticmethod
    def _f(v):
        if v is None:
            return None
        try:
            f = float(v)
            return f if f == f else None
        except Exception:
            return None

    @classmethod
    def _extract_metrics(cls, info: dict) -> dict:
        m = {}
        keys = {
            # valuation
            "trailingPE": "pe_trailing",
            "forwardPE": "pe_forward",
            "priceToBook": "pb",
            "priceToSalesTrailing12Months": "ps",
            "priceToBookTrailing": "pb_trailing",
            "enterpriseToRevenue": "ev_revenue",
            "enterpriseToEbitda": "ev_ebitda",
            "pegRatio": "peg",
            "priceToSalesTrailing12Months": "ps_trailing",
            "dividendYield": "dividend_yield",
            # profitability
            "returnOnEquity": "roe",
            "returnOnAssets": "roa",
            "profitMargins": "net_margin",
            "grossMargins": "gross_margin",
            "operatingMargins": "operating_margin",
            "returnOnCapitalEmployed": "roce",
            # liquidity / solvency
            "currentRatio": "current_ratio",
            "quickRatio": "quick_ratio",
            "debtToEquity": "debt_equity",
            "totalCash": "total_cash",
            "totalDebt": "total_debt",
            # growth
            "earningsGrowth": "earnings_growth",
            "revenueGrowth": "revenue_growth",
            "earningsQuarterlyGrowth": "earnings_q_growth",
            "revenueGrowthQuarterly": "revenue_q_growth",
            # scale
            "marketCap": "market_cap",
            "freeCashflow": "free_cashflow",
            "totalRevenue": "revenue",
            "totalCashPerShare": "cash_per_share",
            "bookValue": "book_value",
            "targetMeanPrice": "target_mean_price",
            "recommendationKey": "recommendation",
            "NumberOfAnalystOpinions": "analyst_count",
            "industry": "industry",
            "sector": "sector",
        }
        for src, dst in keys.items():
            v = cls._f(info.get(src))
            if v is not None:
                m[dst] = v
        return m


# Keep a module-level singleton so providers share caches.
yahoo_provider = YahooProvider()