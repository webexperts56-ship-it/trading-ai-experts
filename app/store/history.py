import json
import os
import sqlite3
import threading

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    symbol TEXT,
    ts TEXT,
    data_json TEXT,
    PRIMARY KEY (symbol, ts)
);
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    horizon TEXT,
    issued_ts TEXT,
    expires_ts TEXT,
    action TEXT,
    probability_up REAL,
    entry_price REAL,
    resolved INTEGER DEFAULT 0,
    actual_return REAL,
    correct INTEGER,
    resolved_ts TEXT,
    UNIQUE (symbol, horizon, issued_ts)
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    symbol TEXT,
    kind TEXT,
    message TEXT,
    data_json TEXT
);
"""

_COLUMNS = ("id", "symbol", "horizon", "issued_ts", "expires_ts", "action",
            "probability_up", "entry_price", "resolved", "actual_return",
            "correct", "resolved_ts")

_PREDICTION_INSERT_COLUMNS = ("symbol", "horizon", "issued_ts", "expires_ts",
                              "action", "probability_up", "entry_price")


class Store:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._connect()
        self._migrate()

    def _connect(self):
        if self.db_path:
            parent = os.path.dirname(os.path.abspath(self.db_path))
            os.makedirs(parent, exist_ok=True)
        self._db = sqlite3.connect(self.db_path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=5000")

    def _migrate(self):
        with self._lock:
            try:
                self._db.executescript(_SCHEMA)
                self._db.commit()
            except Exception:
                self._db.rollback()

    def save_snapshot(self, snap: dict):
        with self._lock:
            try:
                self._db.execute(
                    "INSERT OR REPLACE INTO snapshots (symbol, ts, data_json) "
                    "VALUES (?, ?, ?)",
                    (snap.get("symbol"), snap.get("ts"),
                     json.dumps(snap, default=str)),
                )
                self._db.commit()
            except Exception:
                self._db.rollback()

    def list_snapshots(self, symbol: str, limit: int = 100) -> list:
        with self._lock:
            try:
                cur = self._db.execute(
                    "SELECT data_json FROM snapshots WHERE symbol = ? "
                    "ORDER BY ts DESC LIMIT ?",
                    (symbol, limit),
                )
                rows = cur.fetchall()
            except Exception:
                return []
        out = []
        for (data,) in rows:
            try:
                out.append(json.loads(data))
            except Exception:
                continue
        return out

    def save_prediction(self, symbol, horizon, issued_ts, expires_ts,
                        action, probability_up, entry_price) -> int:
        with self._lock:
            try:
                cur = self._db.execute(
                    "SELECT id FROM predictions "
                    "WHERE symbol = ? AND horizon = ? AND resolved = 0 "
                    "AND expires_ts > ? ORDER BY issued_ts DESC LIMIT 1",
                    (symbol, horizon, issued_ts),
                )
                row = cur.fetchone()
                if row:
                    return row[0]
            except Exception:
                self._db.rollback()
            try:
                self._db.execute(
                    "INSERT INTO predictions (" +
                    ", ".join(_PREDICTION_INSERT_COLUMNS) +
                    ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (symbol, horizon, issued_ts, expires_ts, action,
                     probability_up, entry_price),
                )
                self._db.commit()
                return self._db.execute("SELECT last_insert_rowid()").fetchone()[0]
            except Exception:
                self._db.rollback()
                return -1

    def pending_predictions(self, now: str) -> list:
        with self._lock:
            try:
                cur = self._db.execute(
                    "SELECT " + ", ".join(_COLUMNS) +
                    " FROM predictions WHERE resolved = 0 AND expires_ts <= ?",
                    (now,),
                )
                rows = cur.fetchall()
            except Exception:
                return []
        out = []
        for row in rows:
            pred = dict(zip(_COLUMNS, row))
            pred["correct"] = pred["correct"] if pred["correct"] is not None else None
            out.append(pred)
        return out

    def active_predictions(self):
        """All unresolved predictions (expired or not) for realtime TP/SL watch."""
        with self._lock:
            try:
                cur = self._db.execute(
                    "SELECT " + ", ".join(_COLUMNS) +
                    " FROM predictions WHERE resolved = 0",
                )
                rows = cur.fetchall()
            except Exception:
                return []
        out = []
        for row in rows:
            pred = dict(zip(_COLUMNS, row))
            pred["correct"] = pred["correct"] if pred["correct"] is not None else None
            out.append(pred)
        return out

    def resolve_prediction(self, pred_id, actual_return: float, correct: bool,
                           now):
        with self._lock:
            try:
                self._db.execute(
                    "UPDATE predictions SET resolved = 1, actual_return = ?, "
                    "correct = ?, resolved_ts = ? WHERE id = ?",
                    (actual_return, 1 if correct else 0, now, pred_id),
                )
                self._db.commit()
            except Exception:
                self._db.rollback()

    def add_alert(self, alert: dict):
        with self._lock:
            try:
                data = {k: v for k, v in alert.items() if k not in
                        ("ts", "symbol", "kind", "message")}
                self._db.execute(
                    "INSERT INTO alerts (ts, symbol, kind, message, data_json) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (alert.get("ts"), alert.get("symbol"), alert.get("kind"),
                     alert.get("message"), json.dumps(data, default=str)),
                )
                self._db.commit()
            except Exception:
                self._db.rollback()

    def predictions_summary(self, limit: int = 500) -> dict:
        with self._lock:
            try:
                cur = self._db.execute(
                    "SELECT horizon, correct FROM predictions "
                    "WHERE resolved = 1 ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
                rows = cur.fetchall()
                cur = self._db.execute(
                    "SELECT COUNT(*) FROM predictions WHERE resolved = 0"
                )
                pending = cur.fetchone()[0]
            except Exception:
                return {"resolved": 0, "correct": 0, "hit_rate": 0,
                        "by_horizon": {}, "pending": 0}
        by_horizon = {}
        for horizon, correct in rows:
            entry = by_horizon.setdefault(
                horizon, {"n": 0, "correct": 0, "hit_rate": 0}
            )
            entry["n"] += 1
            if correct:
                entry["correct"] += 1
        for entry in by_horizon.values():
            entry["hit_rate"] = (
                round(entry["correct"] / entry["n"] * 100, 1)
                if entry["n"] else 0
            )
        n = len(rows)
        m = sum(1 for _, correct in rows if correct)
        return {
            "resolved": n,
            "correct": m,
            "wrong": n - m,
            "hit_rate": round(m / n * 100, 1) if n else 0,
            "by_horizon": by_horizon,
            "pending": pending,
        }

    def accuracy(self, limit: int = 1000) -> dict:
        summary = self.predictions_summary(limit)
        by_symbol = {}
        with self._lock:
            try:
                cur = self._db.execute(
                    "SELECT symbol, correct FROM predictions "
                    "WHERE resolved = 1 ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
                rows = cur.fetchall()
            except Exception:
                rows = []
        for symbol, correct in rows:
            entry = by_symbol.setdefault(
                symbol, {"symbol": symbol, "n": 0, "correct": 0, "hit_rate": 0}
            )
            entry["n"] += 1
            if correct:
                entry["correct"] += 1
        for entry in by_symbol.values():
            entry["hit_rate"] = (
                round(entry["correct"] / entry["n"] * 100, 1)
                if entry["n"] else 0
            )
        ranked = sorted(by_symbol.values(),
                        key=lambda e: e["n"], reverse=True)[:14]
        summary["by_symbol"] = ranked
        return summary

    def recent_predictions(self, limit: int = 50) -> list:
        cols = ("id", "symbol", "horizon", "action", "probability_up",
                "entry_price", "actual_return", "correct", "issued_ts",
                "expires_ts", "resolved_ts")
        with self._lock:
            try:
                cur = self._db.execute(
                    "SELECT " + ", ".join(cols) +
                    " FROM predictions ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
                rows = cur.fetchall()
            except Exception:
                return []
        return [dict(zip(cols, row)) for row in rows]

    def recent_alerts(self, limit: int = 50) -> list:
        with self._lock:
            try:
                cur = self._db.execute(
                    "SELECT ts, symbol, kind, message, data_json FROM alerts "
                    "ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
                rows = cur.fetchall()
            except Exception:
                return []
        out = []
        for ts, symbol, kind, message, data in rows:
            alert = {"ts": ts, "symbol": symbol, "kind": kind,
                     "message": message}
            try:
                alert.update(json.loads(data))
            except Exception:
                pass
            out.append(alert)
        return out
