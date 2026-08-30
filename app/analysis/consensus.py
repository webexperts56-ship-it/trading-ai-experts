import threading
import time
from datetime import datetime, timezone

HORIZON_ORDER = ["1H", "6H", "1D", "5D", "1MO"]


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def _dir(score):
    if score >= 5:
        return 1
    if score <= -5:
        return -1
    return 0


class SignalConsensus:
    def __init__(self):
        self._lock = threading.Lock()
        self._result = {"status": "empty", "computed_ts": None}
        self._last_signature = None

    def update(self, snapshots):
        sig = tuple(sorted(snaps.get("symbol", "") + "|" + snaps.get("ts", "")
                           for snaps in snapshots))
        if sig == self._last_signature:
            return
        try:
            result = _compute(snapshots)
        except Exception as e:
            result = {"status": "error", "detail": str(e)[:120]}
        result["computed_ts"] = utcnow()
        with self._lock:
            self._result = result
            self._last_signature = sig

    def snapshot(self):
        with self._lock:
            return dict(self._result)


def _compute(snapshots):
    n_sym = len(snapshots)
    n_sig = 0
    bull = bear = neutral = 0
    prob_sum = 0.0
    score_sum = 0.0
    comp_sum = 0.0
    buy_tp_pct = []
    buy_sl_pct = []
    buys = []
    sells = []
    for snap in snapshots:
        comp = (snap.get("composite") or {}).get("score") or 0.0
        comp_sum += comp
        entry = (snap.get("quote") or {}).get("price")
        for sig in snap.get("signals") or []:
            horizon = sig.get("horizon")
            if horizon not in HORIZON_ORDER:
                continue
            n_sig += 1
            score = sig.get("score") or 0.0
            score_sum += score
            prob_sum += float(sig.get("probability_up") or 0.5)
            direction = _dir(score)
            if direction > 0:
                bull += 1
            elif direction < 0:
                bear += 1
            else:
                neutral += 1
            if entry:
                tp = sig.get("take_profit")
                sl = sig.get("stop_loss")
                if tp and sl:
                    risk = abs(entry - sl) / entry * 100.0
                    reward = abs(tp - entry) / entry * 100.0
                    if direction > 0:
                        buy_tp_pct.append(reward)
                        buy_sl_pct.append(risk)
                    elif direction < 0:
                        buy_tp_pct.append(reward)
                        buy_sl_pct.append(risk)
        top = _signal_of(snap, entry)
        if top:
            if top["score"] > 0:
                buys.append(top)
            elif top["score"] < 0:
                sells.append(top)

    bull_share = round(bull / n_sig * 100, 1) if n_sig else 0.0
    bear_share = round(bear / n_sig * 100, 1) if n_sig else 0.0
    neutral_share = round(neutral / n_sig * 100, 1) if n_sig else 0.0
    avg_composite = round(comp_sum / n_sym, 1) if n_sym else 0.0
    avg_score = round(score_sum / n_sig, 1) if n_sig else 0.0
    avg_prob = round(prob_sum / n_sig, 4) if n_sig else 0.5

    if bull >= bear and bull > 0:
        direction = "BULLISH"
    elif bear > bull and bear > 0:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"
    strength = round(abs(bull - bear) / (bull + bear), 3) if (bull + bear) else 0.0
    net_tilt = round((bull - bear) / n_sig, 3) if n_sig else 0.0

    return {
        "status": "ok",
        "n_symbols": n_sym,
        "n_signals": n_sig,
        "avg_composite": avg_composite,
        "avg_signal_score": avg_score,
        "avg_probability_up": avg_prob,
        "bullish_signals": bull,
        "bearish_signals": bear,
        "neutral_signals": neutral,
        "bullish_share": bull_share,
        "bearish_share": bear_share,
        "neutral_share": neutral_share,
        "net_tilt": net_tilt,
        "consensus_direction": direction,
        "consensus_strength": strength,
        "avg_risk_pct": round(sum(buy_sl_pct) / len(buy_sl_pct), 2) if buy_sl_pct else None,
        "avg_reward_pct": round(sum(buy_tp_pct) / len(buy_tp_pct), 2) if buy_tp_pct else None,
        "top_buys": sorted(buys, key=lambda x: x["score"], reverse=True)[:5],
        "top_sells": sorted(sells, key=lambda x: x["score"])[:5],
    }


def _signal_of(snap, entry):
    best = None
    for sig in snap.get("signals") or []:
        if sig.get("horizon") not in HORIZON_ORDER:
            continue
        score = sig.get("score") or 0.0
        if best is None or abs(score) > abs(best["score"]):
            best = {
                "symbol": snap.get("symbol"),
                "name": snap.get("name"),
                "horizon": sig.get("horizon"),
                "action": sig.get("action"),
                "score": round(score, 1),
                "probability_up": sig.get("probability_up"),
                "entry": entry,
                "take_profit": sig.get("take_profit"),
                "stop_loss": sig.get("stop_loss"),
            }
    return best
