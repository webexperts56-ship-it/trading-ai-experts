from __future__ import annotations

import numpy as np
import pandas as pd

from app.technical import indicators as ind


def _last(s):
    if s is None or isinstance(s, pd.Series) and len(s) == 0:
        return None
    v = float(s.iloc[-1])
    if v != v:
        return None
    return v


def _nan0(v):
    if v is None or v != v:
        return 0.0
    return float(v)


def _clamp(x, lo=-100.0, hi=100.0):
    if x != x:
        return 0.0
    return max(lo, min(hi, x))


def _score(x, scale=1.0):
    return np.tanh(_nan0(x) / max(scale, 1e-9)) * 100.0


def _pattern_name(df, i):
    if i < 1 or i >= len(df):
        return "none"
    prev = df.iloc[i - 1]
    cur = df.iloc[i]
    o, h, l, c = cur["open"], cur["high"], cur["low"], cur["close"]
    po, pc = prev["open"], prev["close"]
    body = abs(c - o)
    range_ = (h - l) if (h - l) != 0 else np.nan
    if range_ != range_:
        return "none"
    upper = h - max(o, c)
    lower = min(o, c) - l
    prev_body = abs(pc - po)
    is_bull_eng = c > o and prev_body > 0 and po > pc and c > po and o < pc
    o_approx = po >= pc
    c_prev = pc if o_approx else po
    o_prev = po if o_approx else pc
    atr_ref = max(range_, 1e-9)
    tiny = 0.08 * atr_ref
    if (c - o) * (po - pc) < 0 and (body > tiny) and (prev_body > tiny):
        if is_bull_eng:
            return "bullish_engulfing"
        return "bearish_engulfing"
    body_small = body <= 0.15 * range_
    wick_bottom = lower >= 1.5 * body and lower >= 2 * upper
    if wick_bottom and upper < 0.5 * body:
        return "hammer"
    wick_top = upper >= 1.5 * body and upper >= 2 * lower
    if wick_top and lower < 0.5 * body:
        return "shooting_star"
    if c == o and body_small:
        return "doji"
    if i >= 2:
        p2 = df.iloc[i - 2]
        prev_body = abs(pc - po)
        body2 = abs(p2["close"] - p2["open"])
        if p2["close"] < p2["open"] and pc > po and c > o:
            if c > (p2["open"] + p2["close"]) / 2 and prev_body > tiny and body2 > tiny:
                return "morning_star"
        if p2["close"] > p2["open"] and pc < po and c < o:
            if c < (p2["open"] + p2["close"]) / 2 and prev_body > tiny and body2 > tiny:
                return "evening_star"
    if wick_bottom and upper >= 0.5 * body:
        return "pin_bottom"
    if wick_top and lower >= 0.5 * body:
        return "pin_top"
    return "none"


_PATTERN_SCORE = {
    "bullish_engulfing": 60.0,
    "bearish_engulfing": -60.0,
    "hammer": 35.0,
    "shooting_star": -35.0,
    "doji": 0.0,
    "morning_star": 50.0,
    "evening_star": -50.0,
    "pin_bottom": 25.0,
    "pin_top": -25.0,
    "none": 0.0,
}


def _momentum_score(df, scale=5.0):
    close = df["close"]
    if len(close) < 21:
        return 0.0
    r5 = ind.roc(close, 5)
    r10 = ind.roc(close, 10)
    r20 = ind.roc(close, 20)
    rw = ind.roc(close, 7)
    s5, s10, s20, sw = 0.0, 0.0, 0.0, 0.0
    if _last(r5) is not None:
        s5 = _score(r5.iloc[-1], scale)
    if _last(r10) is not None:
        s10 = _score(r10.iloc[-1], scale)
    if _last(r20) is not None:
        s20 = _score(r20.iloc[-1], scale)
    if _last(rw) is not None:
        sw = _score(rw.iloc[-1], scale * 1.1)
    return (0.3 * s5 + 0.35 * s10 + 0.25 * s20 + 0.1 * sw)


def _oscillator_score(df):
    close = df["close"]
    r = ind.rsi(close, 14)
    rv = _last(r)
    osc = 0.0
    if rv is not None:
        osc += 0.35 * ((50.0 - rv) / 50.0 * 100.0)
    stoch = ind.stochastic(df, 14, 3)
    sk = _last(stoch["k"])
    sd = _last(stoch["d"])
    if sk is not None and sd is not None:
        k_s = 0.0
        if sk < 20:
            k_s = (20 - sk) / 20 * 100.0
        elif sk > 80:
            k_s = (80 - sk) / 20 * 100.0
        d_s = 0.0
        if sd < 20:
            d_s = (20 - sd) / 20 * 100.0
        elif sd > 80:
            d_s = (80 - sd) / 20 * 100.0
        osc += 0.25 * k_s + 0.15 * d_s
    macd_df = ind.macd(close)
    hist = _last(macd_df["hist"])
    atr_v = _last(ind.atr(df, 14))
    if hist is not None and atr_v is not None and atr_v > 0:
        hist_norm = hist / atr_v
        osc += 0.25 * _score(hist_norm, 1.5)
    return _clamp(osc)


def _trend_score(df):
    close = df["close"]
    if len(close) < 50:
        return 0.0
    sma20 = ind.sma(df["close"], 20)
    sma50 = ind.sma(df["close"], 50)
    ema20 = ind.ema(df["close"], 20)
    ema50 = ind.ema(df["close"], 50)
    price = _last(close)
    vs20 = _last((close / sma20 - 1) * 100)
    vs50 = _last((close / sma50 - 1) * 100)
    score = 0.0
    if vs20 is not None:
        score += 0.25 * _score(vs20, 3.0)
    if vs50 is not None:
        score += 0.25 * _score(vs50, 5.0)
    e20 = _last(ema20)
    e50 = _last(ema50)
    if e20 is not None and e50 is not None and e50 != 0:
        score += 0.2 * _score((e20 - e50) / abs(e50) * 100, 2.0)
    if len(ema20) > 21:
        slope = ema20.diff(20)
        sv = _last(slope)
        ep = _last(ema20.shift(20))
        if sv is not None and ep and ep != 0:
            score += 0.2 * _score(sv / abs(ep) * 100, 2.0)
    adxD = ind.adx(df, 14)
    adxv = _last(adxD["adx"])
    if adxv is not None:
        damp = min(1.0, adxv / 25.0)
        score = score * (0.4 + 0.6 * damp)
    else:
        score *= 0.4
    if price is not None and sma50 is not None and _last(sma50) is not None and price > _last(sma50):
        pass
    return _clamp(score)


def _volume_score(df):
    close = df["close"]
    if len(close) < 40:
        return 0.0
    ob = ind.obv(df)
    ob_slope_short = 0.0
    ob_slope_long = 0.0
    if len(ob) > 21:
        ob_short = ind.roc(ob, 5)
        ob_long = ind.roc(ob, 20)
        s = _last(ob_short)
        l = _last(ob_long)
        if s is not None:
            ob_slope_short = _score(s, 15.0)
        if l is not None:
            ob_slope_long = _score(l, 40.0)
    cmfv = _last(ind.cmf(df, 20))
    cmf_s = _score(cmfv if cmfv is not None else 0.0, 0.5) if cmfv is not None else 0.0
    vol = df["volume"]
    last_v = _last(vol)
    mean_v = _last(vol.rolling(20, min_periods=1).mean())
    rel = 0.0
    if last_v is not None and mean_v and mean_v > 0:
        rel = _score((last_v - mean_v) / mean_v * 100.0, 60.0)
    return _clamp(0.35 * ob_slope_short + 0.25 * ob_slope_long + 0.25 * cmf_s + 0.15 * rel)


def _volatility_score(df):
    close = df["close"]
    atr_v = _last(ind.atr(df, 14))
    price = _last(close)
    bb = ind.bollinger(close, 20, 2)
    score = 0.0
    if atr_v is not None and price and price > 0:
        atr_pct = atr_v / price * 100.0
        base = 1.0
        score -= _score(atr_pct, 3.0) * 1.0
        if atr_pct > 3.0:
            score -= 20.0
    bbw = None
    upper = _last(bb["upper"])
    lower = _last(bb["lower"])
    mid = _last(bb["mid"])
    if upper is not None and lower is not None and mid:
        rng = upper - lower
        if rng != 0 and mid != 0:
            bbw = rng / mid * 100.0
            score -= _score(bbw - 10.0, 10.0) * 0.5
    return _clamp(score)


def _candle_score(df):
    if df is None or len(df) < 2:
        return 0.0
    name = _pattern_name(df, len(df) - 1)
    score = _PATTERN_SCORE.get(name, 0.0)
    cc = _last(df["close"])
    pc = _last(df["close"].shift(1))
    if cc is not None and pc is not None and pc != 0:
        sign = 1.0 if cc > pc else (-1.0 if cc < pc else 0.0)
        score += sign * 10.0
    return _clamp(score)


def feature_subscores(df):
    if df is None or len(df) < 20:
        return {
            "momentum": 0.0,
            "oscillator": 0.0,
            "trend": 0.0,
            "volume": 0.0,
            "volatility": 0.0,
            "candle": 0.0,
        }
    return {
        "momentum": _clamp(_momentum_score(df)),
        "oscillator": _clamp(_oscillator_score(df)),
        "trend": _clamp(_trend_score(df)),
        "volume": _clamp(_volume_score(df)),
        "volatility": _clamp(_volatility_score(df)),
        "candle": _clamp(_candle_score(df)),
    }


def _vwap_z(df):
    close = df["close"]
    vwap = ind.rolling_vwap(df, 20)
    std = close.rolling(20, min_periods=2).std()
    std_v = _last(std)
    vwap_v = _last(vwap)
    close_v = _last(close)
    if std_v is None or vwap_v is None or close_v is None or std_v == 0:
        return 0.0
    return (close_v - vwap_v) / std_v


def _bb_position(df):
    close = df["close"]
    bb = ind.bollinger(close, 20, 2)
    c = _last(close)
    u = _last(bb["upper"])
    l = _last(bb["lower"])
    if c is None or u is None or l is None:
        return 0.5
    rng = u - l
    if rng == 0:
        return 0.5
    return max(0.0, min(1.0, (c - l) / rng))


def _vol_ratio(df):
    vol = df["volume"]
    last_v = _last(vol)
    mean_v = _last(vol.rolling(20, min_periods=1).mean())
    if last_v is None or mean_v is None or mean_v == 0:
        return 0.0
    return last_v / mean_v


def indicator_readings(df):
    close = df["close"]
    macd_df = ind.macd(close)
    stoch = ind.stochastic(df, 14, 3)
    atr_v = _last(ind.atr(df, 14))
    price = _last(close)
    adxD = ind.adx(df, 14)
    vol_ratio = _vol_ratio(df)
    cc = _last(close)
    prev = _last(close.shift(1))
    return {
        "rsi": round(_nan0(_last(ind.rsi(close, 14))), 2),
        "macd_hist": round(_nan0(_last(macd_df["hist"])), 6),
        "macd_signal": round(_nan0(_last(macd_df["signal"])), 6),
        "stoch_k": round(_nan0(_last(stoch["k"])), 2),
        "stoch_d": round(_nan0(_last(stoch["d"])), 2),
        "atr_pct": round((_nan0(atr_v) / _nan0(price) * 100 if _nan0(price) else 0.0), 3),
        "adx": round(_nan0(_last(adxD["adx"])), 2),
        "ema20": round(_nan0(_last(ind.ema(close, 20))), 4),
        "ema50": round(_nan0(_last(ind.ema(close, 50))), 4),
        "sma200": round(_nan0(_last(ind.sma(close, 200))), 4),
        "cmf": round(_nan0(_last(ind.cmf(df, 20))), 4),
        "vwap_z": round(_vwap_z(df), 3),
        "vol_ratio": round(vol_ratio, 3),
        "bb_position": round(_bb_position(df), 3),
        "last_pattern": _pattern_name(df, len(df) - 1) if len(df) else "none",
        "last_close": round(_nan0(cc), 4),
        "roc5": round(_nan0(_last(ind.roc(close, 5))), 3),
        "roc10": round(_nan0(_last(ind.roc(close, 10))), 3),
    }


def price_stats(df, bars_per_tf=60):
    close = df["close"]
    base = {
        "last_close": round(_nan0(_last(close)), 4),
        "change_1m_pct": 0.0,
        "change_5m_pct": 0.0,
        "change_1h_pct": 0.0,
        "change_1d_pct": 0.0,
        "change_5d_pct": 0.0,
    }
    if len(close) < 2:
        return base
    last_v = _last(close)

    def pct_bars(n):
        if len(close) < n + 1:
            return 0.0
        ref = _last(close.shift(n))
        if ref is None or ref == 0:
            return 0.0
        return (last_v - ref) / ref * 100.0

    minutes = max(1, int(bars_per_tf))
    base["change_1m_pct"] = round(pct_bars(max(1, int(round(1 / minutes)))), 3)
    base["change_5m_pct"] = round(pct_bars(max(1, int(round(5 / minutes)))), 3)
    base["change_1h_pct"] = round(pct_bars(max(1, int(round(60 / minutes)))), 3)
    base["change_1d_pct"] = round(pct_bars(max(1, int(round(1440 / minutes)))), 3)
    base["change_5d_pct"] = round(pct_bars(max(1, int(round(5 * 1440 / minutes)))), 3)
    return base


def ml_feature_vector(df):
    close = df["close"]
    macd_df = ind.macd(close)
    stoch = ind.stochastic(df, 14, 3)
    adxD = ind.adx(df, 14)
    price = _nan0(_last(close))
    hist = _nan0(_last(macd_df["hist"]))
    ema20 = _nan0(_last(ind.ema(close, 20)))
    ema50 = _nan0(_last(ind.ema(close, 50)))
    ema200 = _nan0(_last(ind.ema(close, 200)))
    sma200 = _nan0(_last(ind.sma(close, 200)))
    atr_v = _nan0(_last(ind.atr(df, 14)))
    roc5_v = _nan0(_last(ind.roc(close, 5)))
    atr_pct = atr_v / price * 100 if price else 0.0
    realized_vol = _nan0(_last(close.pct_change().rolling(20).std())) * 100 * np.sqrt(252)
    vol_norm_mom = roc5_v / max(atr_pct, 0.05)
    hl_range_pct = (_nan0(_last(df["high"])) - _nan0(_last(df["low"]))) / price * 100 if price else 0.0
    return {
        "rsi": float(_nan0(_last(ind.rsi(close, 14)))),
        "macd_hist_norm": float(hist / price if price else 0.0),
        "stoch_k": float(_nan0(_last(stoch["k"]))),
        "atr_pct": float((atr_v / price * 100 if price else 0.0)),
        "adx": float(_nan0(_last(adxD["adx"]))),
        "cmf": float(_nan0(_last(ind.cmf(df, 20)))),
        "vwap_z": float(_vwap_z(df)),
        "vol_ratio": float(_vol_ratio(df)),
        "bb_position": float(_bb_position(df)),
        "roc5": float(_nan0(_last(ind.roc(close, 5)))),
        "roc10": float(_nan0(_last(ind.roc(close, 10)))),
        "roc20": float(_nan0(_last(ind.roc(close, 20)))),
        "ema_gap_20_50": float((ema20 - ema50) / abs(ema50) * 100 if ema50 else 0.0),
        "ema_gap_50_200": float((ema50 - ema200) / abs(ema200) * 100 if ema200 else 0.0),
        "close_sma200_gap": float((price / sma200 - 1) if sma200 else 0.0),
        "realized_vol": float(realized_vol),
        "vol_norm_mom": float(vol_norm_mom),
        "hl_range_pct": float(hl_range_pct),
    }
