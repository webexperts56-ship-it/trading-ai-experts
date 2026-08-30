from __future__ import annotations

import numpy as np
import pandas as pd

from app.technical import indicators as ind


def _last(s):
    if s is None or isinstance(s, pd.Series) and (len(s) == 0):
        return None
    v = s.iloc[-1]
    if v != v:
        return None
    return float(v)


def _nan0(v):
    if v is None or v != v:
        return 0.0
    return float(v)


def _clamp(x, lo=0.0, hi=100.0):
    if x != x:
        return 0.0
    return max(lo, min(hi, x))


def classify_trend(df):
    close = df["close"]
    empty = {
        "regime": "SIDEWAYS",
        "strength": 0.0,
        "trend_score": 0.0,
        "ema_stack": "mixed",
        "sma_slope": 0.0,
        "adx": 0.0,
    }
    if df is None or len(close) < 60:
        return empty
    ema20 = ind.ema(close, 20)
    ema50 = ind.ema(close, 50)
    sma200 = ind.sma(close, 200)
    sma20 = ind.sma(close, 20)
    price = _last(close)
    e20 = _last(ema20)
    e50 = _last(ema50)
    s200 = _last(sma200)
    if e20 is None or e50 is None or s200 is None or price is None:
        return empty
    if e20 > e50:
        stack = "bullish"
    elif e20 < e50:
        stack = "bearish"
    else:
        stack = "mixed"
    if len(sma20) > 21:
        slope = _last(sma20 - sma20.shift(20))
        ref = _last(sma20.shift(20))
        sma_slope = (slope / abs(ref) * 100) if ref else 0.0
    else:
        sma_slope = 0.0
    score = 0.0
    if e20 > e50 and price > s200:
        score += 60.0
    if e20 < e50 and price < s200:
        score -= 60.0
    if stack == "bullish":
        score += 15.0
    elif stack == "bearish":
        score -= 15.0
    score += _clamp(sma_slope, -40.0, 40.0)
    adxD = ind.adx(df, 14)
    adxv = _nan0(_last(adxD["adx"]))
    if adxv >= 25:
        regime_strength = _clamp(abs(score) * 0.5 + adxv * 1.0)
        regime = "BULL" if score > 0 else ("BEAR" if score < 0 else "SIDEWAYS")
    elif adxv <= 18:
        regime = "SIDEWAYS"
        regime_strength = _clamp(50 - abs(adxv - 18) * 3.0)
    else:
        regime_strength = _clamp(abs(score) * 0.3 + adxv * 0.9)
        regime = "BULL" if score > 0 else ("BEAR" if score < 0 else "SIDEWAYS")
    trend_score = _clamp(score, -100.0, 100.0)
    return {
        "regime": regime,
        "strength": round(regime_strength, 1),
        "trend_score": round(trend_score, 1),
        "ema_stack": stack,
        "sma_slope": round(_nan0(sma_slope), 3),
        "adx": round(adxv, 1),
    }


def market_context(momentum_map):
    if not momentum_map:
        return {
            "regime": "mixed",
            "strength": 0.0,
            "breadth": 0.0,
            "mean_momentum": 0.0,
            "n_up": 0,
            "n_total": 0,
            "context_note": "No data",
        }
    values = [float(v) for v in momentum_map.values() if v is not None and v == v]
    n_total = len(values)
    n_up = sum(1 for v in values if v > 0)
    breadth = (n_up / n_total) if n_total else 0.0
    mean_mom = (sum(values) / n_total) if n_total else 0.0
    if breadth > 0.6 and mean_mom > 0:
        regime = "bull"
        strength = _clamp((breadth - 0.5) * 120 + min(abs(mean_mom), 3) * 20)
        note = "Broad uptrend"
    elif breadth < 0.4 and mean_mom < 0:
        regime = "bear"
        strength = _clamp((0.5 - breadth) * 120 + min(abs(mean_mom), 3) * 20)
        note = "Risk-off"
    else:
        regime = "mixed"
        strength = _clamp(100 - abs(breadth - 0.5) * 200)
        note = "Choppy market"
    return {
        "regime": regime,
        "strength": round(strength, 1),
        "breadth": round(breadth, 3),
        "mean_momentum": round(mean_mom, 3),
        "n_up": n_up,
        "n_total": n_total,
        "context_note": note,
    }
