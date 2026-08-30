from __future__ import annotations

import numpy as np
import pandas as pd


def _series(x):
    if isinstance(x, pd.Series):
        return x
    return pd.Series(x, dtype=float)


def sma(df, n=20):
    x = _series(df["close"] if isinstance(df, pd.DataFrame) else df)
    return x.rolling(window=n, min_periods=1).mean()


def ema(df, n=20):
    x = _series(df["close"] if isinstance(df, pd.DataFrame) else df)
    return x.ewm(span=n, adjust=False).mean()


def rsi(close, n=14):
    c = _series(close)
    delta = c.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    if up.shape[0] < 2:
        return pd.Series(np.nan, index=c.index)
    roll_up = up.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    roll_down = down.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    rs = roll_up / roll_down.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    out = out.where(roll_down != 0, 100.0)
    out = out.where(~((roll_up == 0) & (roll_down == 0)), 50.0)
    out.iloc[: n - 1] = np.nan
    return out


def macd(close, fast=12, slow=26, signal=9):
    c = _series(close)
    fast_ema = c.ewm(span=fast, adjust=False).mean()
    slow_ema = c.ewm(span=slow, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({
        "macd": macd_line,
        "signal": signal_line,
        "hist": hist,
    })


def bollinger(close, n=20, k=2):
    c = _series(close)
    mid = c.rolling(window=n, min_periods=1).mean()
    std = c.rolling(window=n, min_periods=1).std(ddof=0)
    upper = mid + k * std
    lower = mid - k * std
    return pd.DataFrame({"mid": mid, "upper": upper, "lower": lower})


def stochastic(df, n=14, d=3):
    low_n = df["low"].rolling(window=n, min_periods=1).min()
    high_n = df["high"].rolling(window=n, min_periods=1).max()
    rng = (high_n - low_n).replace(0, np.nan)
    k = ((df["close"] - low_n) / rng) * 100
    k = k.fillna(50.0)
    kd = k.rolling(window=d, min_periods=1).mean()
    return pd.DataFrame({"k": k, "d": kd})


def atr(df, n=14):
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    tr.iloc[0] = df["high"].iloc[0] - df["low"].iloc[0]
    out = tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    out.iloc[: n - 1] = np.nan
    return out


def adx(df, n=14):
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    plus_dm = pd.Series(plus_dm, index=df.index, dtype=float)
    minus_dm = pd.Series(minus_dm, index=df.index, dtype=float)
    plus_dm.iloc[0] = 0.0
    minus_dm.iloc[0] = 0.0
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    tr.iloc[0] = df["high"].iloc[0] - df["low"].iloc[0]
    atr_w = tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean() / atr_w.replace(0, np.nan)
    minus_di = 100.0 * minus_dm.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean() / atr_w.replace(0, np.nan)
    plus_di = plus_di.fillna(0.0)
    minus_di = minus_di.fillna(0.0)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    dx = dx.fillna(0.0)
    adx = dx.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    start = max(n * 2 - 1, n - 1)
    adx.iloc[:start] = np.nan
    return pd.DataFrame({"adx": adx, "plus_di": plus_di, "minus_di": minus_di})


def obv(df):
    direction = np.sign(df["close"].diff()).fillna(0)
    out = (direction * df["volume"]).cumsum()
    return out


def cmf(df, n=20):
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / (2.0 * rng)
    mfm = mfm.fillna(0.0)
    mfv = mfm * df["volume"]
    sum_mfv = mfv.rolling(window=n, min_periods=1).sum()
    sum_vol = df["volume"].rolling(window=n, min_periods=1).sum()
    return sum_mfv / sum_vol.replace(0, np.nan)


def roc(close, n=10):
    c = _series(close)
    shifted = c.shift(n)
    out = (c - shifted) / shifted.replace(0, np.nan) * 100.0
    return out


def rolling_vwap(df, n=20):
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = tp * df["volume"]
    vol = df["volume"].rolling(window=n, min_periods=1).sum()
    return pv.rolling(window=n, min_periods=1).sum() / vol.replace(0, np.nan)
