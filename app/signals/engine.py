import math

import pandas as pd

from app.snapshot import (
    Snapshot,
    HorizonSignal,
    HORIZON_ORDER,
    action_for_score,
    utcnow,
)
from app.data.base import CandleStore
from app.technical.features import (
    feature_subscores,
    indicator_readings,
    price_stats,
    ml_feature_vector,
)
from app.trend.regime import classify_trend
from app.signals.horizons import HORIZON_CONFIG, BLEND_TIMEFRAMES, horizon_config
from app.signals.model import predict

BARS_PER_TF = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

RISK_PCT_BY_HORIZON = {
    "1H": 0.5,
    "6H": 1.0,
    "1D": 1.5,
    "5D": 3.0,
    "1MO": 6.0,
}

RR = 2.0

# Confidence-based target scaling.
# Reward (target distance) scales UP with confidence/probability, while the
# stop stays fixed at the per-horizon risk level. So stronger conviction ->
# larger reward-to-risk, weaker conviction -> smaller target.
RR_MIN = 1.5
RR_MAX = 4.0
CONF_LO = 30.0   # confidence at/below -> RR_MIN
CONF_HI = 90.0   # confidence at/above -> RR_MAX


def _confidence_from_sig(sig) -> float:
    conf = getattr(sig, "confidence", None) or 0.0
    if conf <= 0:
        prob = sig.probability_up or 50.0
        conf = abs(prob - 50.0) * 2.0 + 50.0
    return float(conf)


def _target_rr(sig) -> float:
    conf = _confidence_from_sig(sig)
    conf = max(CONF_LO, min(CONF_HI, conf))
    frac = (conf - CONF_LO) / (CONF_HI - CONF_LO) if CONF_HI > CONF_LO else 1.0
    return RR_MIN + (RR_MAX - RR_MIN) * frac


def _apply_tp_sl(signals, entry):
    if not entry:
        return
    for sig in signals:
        risk_pct = RISK_PCT_BY_HORIZON.get(sig.horizon)
        if risk_pct is None:
            continue
        step = entry * risk_pct / 100.0
        rr = _target_rr(sig)
        if sig.score > 0:
            sig.take_profit = round(entry + rr * step, 8)
            sig.stop_loss = round(entry - step, 8)
        elif sig.score < 0:
            sig.stop_loss = round(entry + step, 8)
            sig.take_profit = round(entry - rr * step, 8)
        else:
            sig.take_profit = None
            sig.stop_loss = None


def _compute_frames(store):
    frames = {}
    for tf in BLEND_TIMEFRAMES:
        if tf not in store.timeframes:
            continue
        df = store.get(tf)
        if df is None or len(df) < 25:
            continue
        bars = BARS_PER_TF.get(tf, 1)
        subscores = feature_subscores(df)
        readings = indicator_readings(df)
        stats = price_stats(df, bars)
        frames[tf] = {
            "df": df,
            "subscores": subscores,
            "readings": readings,
            "stats": stats,
        }
    return frames


def _pick_primary_tf(frames):
    if "1d" in frames:
        return "1d"
    for tf in ["1h", "15m", "5m"]:
        if tf in frames:
            return tf
    return None


def _nearest_long_tf(store):
    for tf in ["1d", "1h", "15m", "5m"]:
        if tf in store.timeframes:
            df = store.get(tf)
            if df is not None and len(df) >= 25:
                return tf, df
    for tf in store.timeframes:
        df = store.get(tf)
        if df is not None and len(df) >= 25:
            return tf, df
    return None, None


def _available_categories(weights, have_fund, have_candle):
    cats = ["momentum", "oscillator", "trend", "volume"]
    if have_candle:
        cats.append("candle")
    if have_fund:
        cats.append("fundamental")
    return cats


def _blended_categories(frames, tf_blend, primary_scales, primary_tf):
    blended = {}
    present = [tf for tf in BLEND_TIMEFRAMES if tf in frames and tf_blend.get(tf)]
    if not present and primary_scales is not None:
        present = [primary_tf]
    total_weight = sum(tf_blend.get(tf, 0.0) for tf in present)
    if total_weight <= 0:
        return {}
    for cat in ["momentum", "oscillator", "trend", "volume", "volatility", "candle"]:
        acc = 0.0
        for tf in present:
            w = tf_blend.get(tf, 0.0)
            if cat == "volatility":
                sub = frames[tf]["subscores"].get("volatility", 0.0)
            else:
                sub = frames[tf]["subscores"].get(cat, 0.0)
            acc += w * sub
        blend_val = acc / total_weight
        blend_time = tf_blend.get(primary_tf, 0.0) if primary_tf in frames else 0.0
        scalar = blend_time
        blended[cat] = blend_val
        if primary_scales is not None and scalar > 0 and primary_scales.get(cat) is not None:
            blended[cat] = primary_scales[cat]
    return blended


def _analyze_frames(meta, frames, primary_tf, store, fundamental, market_ctx, models, quote=None):
    have_fund = fundamental is not None
    have_candle = any("candle" in frames[tf]["subscores"] and frames[tf]["subscores"]["candle"] is not None for tf in frames)

    primary_df = frames[primary_tf]["df"] if primary_tf in frames else None
    primary_scales = None
    if primary_df is not None:
        primary_scales = {"momentum": None, "oscillator": None, "trend": None, "volume": None, "volatility": None, "candle": None}
        for cat in primary_scales:
            primary_scales[cat] = frames[primary_tf]["subscores"].get(cat, 0.0)

    technical = {}
    for tf in BLEND_TIMEFRAMES:
        if tf in frames:
            technical[tf] = {
                "readings": frames[tf]["readings"],
                "subscores": frames[tf]["subscores"],
                "stats": frames[tf]["stats"],
            }
    if "1d" in frames:
        technical["daily"] = frames["1d"]["readings"]
    elif primary_tf in frames:
        technical["daily"] = frames[primary_tf]["readings"]

    trend = {}
    if primary_df is not None:
        trend = classify_trend(primary_df)
        trend["primary_timeframe"] = primary_tf
        trend["market_context"] = market_ctx if market_ctx is not None else {}

    signals = []
    weights_used_per_horizon = {}
    for cfg in HORIZON_CONFIG:
        key = cfg["key"]
        tf_blend = cfg["tf_blend"]
        blended = _blended_categories(frames, tf_blend, primary_scales, primary_tf)
        weights = dict(cfg["category_weights"])
        want = _available_categories(weights, have_fund, have_candle)
        available_weights = {c: weights[c] for c in want}
        wsum = sum(available_weights.values())
        if wsum <= 0:
            available_weights = {c: 1.0 for c in want}
            wsum = len(want)
        norm_weights = {c: available_weights[c] / wsum for c in want}

        score = 0.0
        drivers = {}
        for cat in want:
            if cat == "fundamental":
                cat_val = fundamental.fundamental_score if have_fund else 0.0
                if not have_fund:
                    cat_val = 0.0
            else:
                cat_val = blended.get(cat, 0.0)
            weighted = norm_weights[cat] * cat_val
            drivers[cat] = round(weighted, 4)
            score += weighted

        vol_norm = 0.0
        vol_sub = blended.get("volatility", 0.0)
        if vol_sub is not None:
            vol_norm = min(1.0, abs(vol_sub) / 100.0)
        adjusted = score
        if vol_norm > 0:
            adjusted = score * (1.0 - cfg["vol_penalty"] * vol_norm)
        adjusted = max(-100.0, min(100.0, adjusted))

        probability_up = 0.5 + 0.5 * math.tanh(adjusted / 55.0)

        ml_present = False
        ml_p = None
        model = models.get(key)
        if model is not None and primary_df is not None:
            fv = ml_feature_vector(primary_df)
            ml_p = predict(model, fv)
            if ml_p is not None:
                ml_present = True
                probability_up = 0.55 * probability_up + 0.45 * ml_p

        base_conf = min(100.0, abs(adjusted) + 30.0)
        conf = base_conf * (1.0 - 0.6 * vol_norm)
        if ml_present:
            both_up = probability_up > 0.55 and ml_p > 0.55
            both_down = probability_up < 0.45 and ml_p < 0.45
            if both_up or both_down:
                conf = min(100.0, conf + 8.0)
            else:
                conf = max(0.0, conf - 6.0)
        conf = max(0.0, min(100.0, conf))
        conf = max(conf, 5.0)

        signal = HorizonSignal(
            horizon=key,
            seconds=cfg["seconds"],
            score=round(adjusted, 4),
            action=action_for_score(adjusted),
            probability_up=round(probability_up, 4),
            confidence=round(conf, 2),
            drivers=drivers,
            ml_probability=round(ml_p, 4) if ml_p is not None else None,
        )
        signals.append(signal)
        weights_used_per_horizon[key] = norm_weights

    signals_sorted = sorted(signals, key=lambda s: HORIZON_ORDER.index(s.horizon))

    wsum = 0.0
    comp_sum = 0.0
    for idx, sig in enumerate(signals_sorted):
        mult = 1.25 if idx >= len(HORIZON_ORDER) - 3 else 1.0
        wsum += mult
        comp_sum += sig.score * mult
    comp = comp_sum / wsum if wsum else 0.0
    comp = max(-100.0, min(100.0, comp))
    comp_action = action_for_score(comp)
    if comp >= 25:
        bias = "LONG"
    elif comp <= -25:
        bias = "SHORT"
    else:
        bias = "NEUTRAL"
    composite = {
        "score": round(comp, 4),
        "action": comp_action,
        "bias": bias,
    }

    fact = fundamental.to_dict() if have_fund else {"score": 0, "health": 0, "valuation": 0, "note": "no data"}

    quote_dict = {}
    if quote is not None:
        quote_dict = quote.to_dict()
    else:
        daily_read = technical.get("daily")
        if isinstance(daily_read, dict) and daily_read.get("last_close") is not None:
            quote_dict = {"price": daily_read["last_close"]}

    _apply_tp_sl(signals_sorted, quote_dict.get("price"))

    return Snapshot(
        symbol=meta.get("symbol", ""),
        name=meta.get("name", ""),
        asset_class=meta.get("asset_class", ""),
        market=meta.get("market", ""),
        provider=meta.get("provider", ""),
        ts=utcnow().isoformat(),
        quote=quote_dict,
        fundamental=fact,
        technical=technical,
        trend=trend,
        signals=signals_sorted,
        composite=composite,
        meta=meta,
    )


def analyze(meta, store, quote, fundamental, market_ctx=None, models=None):
    if models is None:
        models = {}
    frames = _compute_frames(store)
    if not frames:
        primary_tf = None
    else:
        primary_tf = _pick_primary_tf(frames)
    return _analyze_frames(meta, frames, primary_tf, store, fundamental, market_ctx, models, quote)


def analyze_daily_only(meta, df, fundamental, models=None):
    if models is None:
        models = {}

    class _TempStore:
        def __init__(self, frame):
            self._frame = frame

        @property
        def timeframes(self):
            return ["1d"]

        def get(self, tf, limit=None):
            if tf == "1d":
                if limit is not None:
                    return self._frame.tail(limit)
                return self._frame
            return None

    store = _TempStore(df)
    frames = _compute_frames(store)
    primary_tf = "1d" if "1d" in frames else None
    snap = _analyze_frames(meta, frames, primary_tf, store, fundamental, None, models)
    for sig in snap.signals:
        if sig.horizon in ("1MIN", "5MIN", "1H", "6H"):
            sig.confidence = round(max(0.0, min(100.0, sig.confidence * 0.5)), 2)
    return snap


def build_feature_vector_for_horizon(snapshot, primary_tf_df):
    if primary_tf_df is None:
        return None
    try:
        return ml_feature_vector(primary_tf_df)
    except Exception:
        return None
