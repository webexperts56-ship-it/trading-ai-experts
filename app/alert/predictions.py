import os
import time
from datetime import datetime, timedelta, timezone

from app.snapshot import HORIZON_ORDER, TO_SECONDS, utcnow
from app.alert.notifier import notifier

_MINUTE_HORIZONS = {"1MIN", "5MIN"}
_SIGNIFICANT_MINUTE = 0.1
_SIGNIFICANT_OTHER = 0.3
_ACCURACY_GATE = float(os.environ.get("SIGNAL_ACCURACY_GATE", "8.0"))
# Confidence at/above which a signal is treated as "must-trade / urgent":
# gets a loud, attention-forcing notification.
_URGENT_CONF = float(os.environ.get("SIGNAL_URGENT_CONF", "75"))

_NEUTRAL_ACTIONS = {"NEUTRAL", "HOLD", "SELL_NEUTRAL", "BUY_NEUTRAL"}
_UP_ACTIONS = {"STRONG_BUY", "BUY", "STRONG_BUY_NEUTRAL"}
_DOWN_ACTIONS = {"STRONG_SELL", "SELL"}


def _psx_open(now: datetime) -> bool:
    try:
        from zoneinfo import ZoneInfo
        local = now.astimezone(ZoneInfo("Asia/Karachi"))
    except Exception:
        local = now.astimezone(timezone(timedelta(hours=5)))
    if local.weekday() >= 5:
        return False
    minutes_of_day = local.hour * 60 + local.minute
    return 9 * 60 + 30 <= minutes_of_day <= 15 * 60 + 35


def _market_closed(snap: dict, now: datetime) -> bool:
    if (snap.get("asset_class") or snap.get("market")) == "crypto":
        return False
    return not _psx_open(now)


def _action_dir(action: str):
    if action in _UP_ACTIONS:
        return 1
    if action in _DOWN_ACTIONS:
        return -1
    return 0


def _significant_threshold(horizon: str) -> float:
    return _SIGNIFICANT_MINUTE if horizon in _MINUTE_HORIZONS else _SIGNIFICANT_OTHER


def _prob_confidence(prob):
    try:
        prob = float(prob)
    except (TypeError, ValueError):
        return 50.0
    return abs(prob - 50.0) * 2.0 + 50.0


class PredictionMonitor:
    def __init__(self, state, store, price_getter, notifier=None):
        self.state = state
        self.store = store
        self.price_getter = price_getter
        self.notifier = notifier if notifier is not None else notifier_singleton

    def ingest(self, snap: dict):
        symbol = snap.get("symbol")
        signals = snap.get("signals") or []
        now = utcnow().isoformat()
        if _market_closed(snap, datetime.now(timezone.utc)):
            return
        quote = snap.get("quote") or {}
        entry = quote.get("price")
        if entry is None:
            tech = snap.get("technical") or {}
            entry = tech.get("daily", {}).get("last_close") if isinstance(
                tech.get("daily"), dict) else None
        if entry is None:
            entry = quote.get("last_price")
        if entry is None:
            return
        for sig in signals:
            horizon = sig.get("horizon")
            if horizon not in _HORIZON_SET:
                continue
            if horizon in _MINUTE_HORIZONS:
                continue
            action = sig.get("action")
            try:
                prob = float(sig.get("probability_up") or 0.5)
                if prob <= 1.0:
                    prob *= 100.0
            except (TypeError, ValueError):
                prob = 50.0
            if _action_dir(action) == 0:
                continue
            if abs(prob - 50.0) < _ACCURACY_GATE:
                continue
            try:
                seconds = float(sig.get("seconds") or TO_SECONDS.get(horizon, 0))
            except (TypeError, ValueError):
                seconds = float(TO_SECONDS.get(horizon, 0))
            if seconds <= 0:
                continue
            expires = now
            try:
                from datetime import timedelta
                expires_ts = (utcnow() + timedelta(seconds=seconds)).isoformat()
            except Exception:
                expires_ts = now
            self.store.save_prediction(
                symbol, horizon, now, expires_ts, action, prob, entry,
            )
            self._notify_signal(symbol, horizon, action, prob, entry, sig, now)

    def _notify_signal(self, symbol, horizon, action, prob, entry, sig, now):
        direction = _action_dir(action)
        if direction == 0:
            return
        ntype = "BUY" if direction > 0 else "SELL"
        name = self._lookup_name(symbol)
        label = name or symbol
        confidence = sig.get("confidence")
        tp, sl = self._tp_sl_for(horizon, entry, direction, confidence)
        entry_show = self._round(entry)
        prob_show = int(round(prob))
        word = "BUY" if direction > 0 else "SELL"
        urgent = self._is_urgent(action, confidence)
        if urgent:
            ntype = "STRONG_BUY" if direction > 0 else "STRONG_SELL"
        conf_txt = f" | confidence {round(confidence)}%" if confidence is not None else ""
        if urgent:
            title = f"TRADING AI : ABHI LE LO — STRONG {word} {label} ({round(confidence if confidence is not None else prob)}%)"
            message = (
                f"🔥 {label} {horizon} — HIGH CONFIDENCE {word} SIGNAL!\n"
                f"ENTRY {entry_show} | P={prob_show}%{conf_txt}\n"
                f"ABHI KHARIDO / LE LO. TP {self._round(tp) if tp else '--'} / SL {self._round(sl) if sl else '--'}"
            )
        else:
            title = f"Trading AI : {ntype} SIGNAL"
            message = (
                f"{word} NOW: {label} {horizon} @ {entry_show} "
                f"(P={prob_show}%{conf_txt}). "
                f"TP {self._round(tp) if tp else '--'} / SL {self._round(sl) if sl else '--'}"
            )
        alert = {
            "ts": now,
            "symbol": symbol,
            "name": name,
            "kind": ntype,
            "type": ntype,
            "horizon": horizon,
            "action": action,
            "entry_price": entry_show,
            "take_profit": self._round(tp) if tp else None,
            "stop_loss": self._round(sl) if sl else None,
            "probability": prob_show,
            "confidence": round(confidence, 1) if confidence is not None else None,
            "urgent": urgent,
            "notification_title": title,
            "message": message,
        }
        try:
            self._call_notifier(alert)
        except Exception:
            pass
        try:
            self.state.add_alert(alert)
        except Exception:
            pass

    @staticmethod
    def _is_urgent(action, confidence):
        if action in ("STRONG_BUY", "STRONG_SELL"):
            return True
        try:
            return float(confidence) >= _URGENT_CONF
        except (TypeError, ValueError):
            return False

    def tick(self):
        now = utcnow().isoformat()
        # Realtime watch: any unresolved prediction can hit TP/SL before expiry.
        # Those get resolved + alerted immediately so the user can sell right away.
        active = self.store.active_predictions()
        for pred in active:
            symbol = pred["symbol"]
            price = self._safe_price(symbol)
            if price is None:
                continue
            entry = pred["entry_price"]
            if not entry:
                continue
            direction = _action_dir(pred["action"])
            if direction == 0:
                continue
            actual_return = (price / entry - 1.0) * 100.0
            correct = (actual_return > 0 and direction > 0) or \
                      (actual_return < 0 and direction < 0)
            if self._tp_sl_hit(pred, price, direction):
                self._handle_resolution(pred, price, actual_return, correct, now, force_tp_sl=True)
        # Expired-but-unresolved: normal end-of-horizon resolution.
        pending = self.store.pending_predictions(now)
        for pred in pending:
            symbol = pred["symbol"]
            price = self._safe_price(symbol)
            if price is None:
                continue
            entry = pred["entry_price"]
            if not entry:
                continue
            actual_return = (price / entry - 1.0) * 100.0
            direction = _action_dir(pred["action"])
            if direction == 0:
                continue
            correct = (actual_return > 0 and direction > 0) or \
                      (actual_return < 0 and direction < 0)
            if pred.get("resolved"):
                continue
            self._handle_resolution(pred, price, actual_return, correct, now)

    def _tp_sl_hit(self, pred, price, direction):
        try:
            prob = float(pred["probability_up"])
        except (TypeError, ValueError):
            prob = 50.0
        tp, sl = self._tp_sl_for(pred["horizon"], pred["entry_price"], direction, _prob_confidence(prob))
        if tp is None or sl is None or not pred.get("entry_price"):
            return False
        if direction > 0:
            return price >= float(tp) or price <= float(sl)
        return price <= float(tp) or price >= float(sl)

    def _handle_resolution(self, pred, price, actual_return, correct, now, force_tp_sl=False):
        horizon = pred["horizon"]
        threshold = _significant_threshold(horizon)
        try:
            prob = float(pred["probability_up"])
        except (TypeError, ValueError):
            prob = 50.0
        strong = prob >= 65.0 or prob <= 35.0
        significant = abs(actual_return) >= threshold
        direction = _action_dir(pred["action"])
        expected_dir = "up" if direction > 0 else "down"
        actual_dir = "up" if actual_return > 0 else ("down" if actual_return < 0 else "flat")
        tp, sl = self._tp_sl_for(horizon, pred["entry_price"], direction, _prob_confidence(prob))
        tp_hit = False
        sl_hit = False
        if tp is not None and sl is not None and pred.get("entry_price"):
            if direction > 0:
                tp_hit = price >= float(tp)
                sl_hit = price <= float(sl)
            else:
                tp_hit = price <= float(tp)
                sl_hit = price >= float(sl)
        if tp_hit:
            kind = "TAKE_PROFIT"
        elif sl_hit:
            kind = "STOP_LOSS"
        elif correct:
            kind = "CORRECT"
        elif significant or strong:
            kind = "WRONG"
        else:
            kind = "MISS"
        name = self._lookup_name(pred["symbol"])
        exit_price = self._round(price)
        entry_show = self._round(pred["entry_price"])
        ret_show = round(actual_return, 2)
        prob_show = int(round(prob))
        label = name or pred["symbol"]
        direction_word = "BUY" if direction > 0 else "SELL"
        if kind == "TAKE_PROFIT":
            verdict = "target complete, profit lock"
            title = "Trading AI : TARGET COMPLETE"
        elif kind == "STOP_LOSS":
            verdict = "stop loss hit, loss cut"
            title = "Trading AI : STOP LOSS HIT"
        elif kind == "CORRECT":
            verdict = "prediction sahi nikli, direction me"
            title = "Trading AI : PREDICTION CORRECT"
        elif kind == "WRONG":
            verdict = "price aapke against gaya"
            title = "Trading AI : PREDICTION WRONG"
        else:
            verdict = "koi movement nahi"
            title = "Trading AI : NO MOVEMENT"
        message = (
            f"{label} {horizon} {direction_word}: entry {entry_show} -> "
            f"{ret_show:+}% {verdict}. TP {self._round(tp) if tp else '--'} / "
            f"SL {self._round(sl) if sl else '--'}"
        )
        alert = {
            "ts": now,
            "symbol": pred["symbol"],
            "name": name,
            "kind": kind,
            "type": kind,
            "horizon": horizon,
            "action": pred["action"],
            "entry_price": entry_show,
            "exit_price": exit_price,
            "actual_return": ret_show,
            "take_profit": self._round(tp) if tp else None,
            "stop_loss": self._round(sl) if sl else None,
            "probability": prob_show,
            "notification_title": title,
            "message": message,
        }
        self.store.resolve_prediction(pred["id"], actual_return, correct, now)
        try:
            self._call_notifier(alert)
        except Exception:
            pass
        try:
            self.state.add_alert(alert)
        except Exception:
            pass

    def _call_notifier(self, alert):
        if self.notifier is None:
            return
        fire = getattr(self.notifier, "fire", None)
        if callable(fire) and fire is not self.notifier:
            fire(alert)
        elif callable(self.notifier):
            self.notifier(alert)

    def run_loop(self, interval: float = 8.0):
        while True:
            try:
                self.tick()
            except Exception:
                pass
            time.sleep(interval)

    def _safe_price(self, symbol):
        try:
            price = self.price_getter(symbol)
            if price is None:
                return None
            return float(price)
        except Exception:
            return None

    def _lookup_name(self, symbol):
        try:
            snap = self.state.get_snapshot(symbol)
            if snap:
                return snap.get("name")
            return None
        except Exception:
            return None

    _RISK_PCT = {"6H": 1.0, "1D": 1.5, "5D": 3.0, "1MO": 6.0}
    _RR_MIN = 1.5
    _RR_MAX = 4.0
    _CONF_LO = 30.0
    _CONF_HI = 90.0

    @classmethod
    def _target_rr(cls, confidence):
        if not confidence:
            return 2.0
        conf = max(cls._CONF_LO, min(cls._CONF_HI, float(confidence)))
        frac = (conf - cls._CONF_LO) / (cls._CONF_HI - cls._CONF_LO)
        return cls._RR_MIN + (cls._RR_MAX - cls._RR_MIN) * frac

    @classmethod
    def _tp_sl_for(cls, horizon, entry, direction, confidence=None):
        risk_pct = cls._RISK_PCT.get(horizon)
        if not entry or risk_pct is None:
            return None, None
        entry = float(entry)
        step = entry * risk_pct / 100.0
        rr = cls._target_rr(confidence)
        if direction > 0:
            return round(entry + rr * step, 8), round(entry - step, 8)
        if direction < 0:
            return round(entry - rr * step, 8), round(entry + step, 8)
        return None, None

    @staticmethod
    def _round(value):
        if value is None:
            return None
        if abs(value) >= 100:
            return round(value, 0)
        if abs(value) >= 1:
            return round(value, 2)
        return round(value, 6)


_HORIZON_SET = set(HORIZON_ORDER)
notifier_singleton = notifier
