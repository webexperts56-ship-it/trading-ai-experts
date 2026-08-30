import json
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

try:
    from config import CONFIG
except Exception:
    CONFIG = None

STATIC_DIR = Path(__file__).parent / "static"

_state = None
_store = None
_crowd = None
_consensus = None


def bind(state, store, crowd=None, consensus=None):
    global _state, _store, _crowd, _consensus
    _state = state
    _store = store
    _crowd = crowd
    _consensus = consensus


def _iso():
    return datetime.now(timezone.utc).isoformat()


def _stats():
    if _state is None:
        return 0, 0
    return len(_state.all_snapshots()), len(_state.recent_alerts(500))


def _alert_id(alert):
    return alert.get("ts") or alert.get("id") or (alert.get("symbol") + str(alert.get("ts")))


app = FastAPI(title="Trading AI Experts", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/health")
def health():
    n_snap, n_alerts = _stats()
    return {"status": "ok", "time": _iso(), "snapshots": n_snap, "alerts": n_alerts}


@app.get("/api/universe")
def universe():
    meta = []
    if CONFIG is not None:
        try:
            meta = list(CONFIG.universe.all())
        except Exception:
            meta = []
    ctx = _state.get_market_ctx() if _state is not None else {}
    return {"universe": meta, "market_context": ctx}


@app.get("/api/snapshots")
def snapshots():
    if _state is None:
        raise HTTPException(status_code=503, detail="state not bound")
    return {
        "snapshots": _state.all_snapshots(),
        "market_context": _state.get_market_ctx(),
        "ts": _iso(),
    }


@app.get("/api/snapshot/{symbol}")
def snapshot(symbol: str):
    if _state is None:
        raise HTTPException(status_code=503, detail="state not bound")
    snap = _state.get_snapshot(symbol)
    if snap is None:
        raise HTTPException(status_code=404, detail="not found")
    return snap


@app.get("/api/alerts")
def alerts(limit: int = 100):
    limit = max(1, min(limit, 1000))
    if _state is not None:
        out = _state.recent_alerts(limit)
        if out:
            return out
    if _store is not None:
        return _store.recent_alerts(limit)
    return []


@app.get("/api/metrics")
def metrics():
    snapshots = 0
    alerts = []
    if _state is not None:
        snapshots = len(_state.all_snapshots())
        alerts = _state.recent_alerts(500)
    breakdown = {}
    for alert in alerts:
        kind = alert.get("kind") or "unknown"
        breakdown[kind] = breakdown.get(kind, 0) + 1
    predictions = _store.predictions_summary() if _store is not None else None
    return {
        "snapshots": snapshots,
        "alerts": len(alerts),
        "predictions": predictions,
        "alert_breakdown": breakdown,
    }


@app.get("/api/predictions")
def predictions(limit: int = 50):
    if _store is None:
        raise HTTPException(status_code=503, detail="store not bound")
    limit = max(1, min(limit, 1000))
    return _store.recent_predictions(limit)


@app.get("/api/accuracy")
def accuracy():
    if _store is None:
        raise HTTPException(status_code=503, detail="store not bound")
    from app.alert.predictions import _ACCURACY_GATE
    result = _store.accuracy()
    result["accuracy_gate"] = _ACCURACY_GATE
    return result


@app.get("/api/consensus")
def consensus():
    if _consensus is None:
        return {"status": "unavailable"}
    return _consensus.snapshot()


@app.get("/api/history/{symbol}")
def history(symbol: str, limit: int = 100):
    limit = max(1, min(limit, 1000))
    if _store is None:
        raise HTTPException(status_code=503, detail="store not bound")
    return _store.list_snapshots(symbol, limit)


@app.post("/api/refresh")
def refresh():
    if _state is None:
        raise HTTPException(status_code=503, detail="state not bound")
    return {
        "note": "engine is auto-refreshing; this endpoint returns current state",
        "snapshots": _state.all_snapshots(),
        "ts": _iso(),
    }


@app.post("/api/alerts/demo")
def demo_alert():
    if _state is None:
        raise HTTPException(status_code=503, detail="state not bound")
    from app.alert.notifier import notifier as _notifier
    alert = {
        "ts": _iso(),
        "symbol": "BTC",
        "name": "BTC",
        "kind": "PREDICTION_SUCCESS",
        "horizon": "1D",
        "action": "BUY",
        "entry_price": 61000.0,
        "exit_price": 62100.0,
        "actual_return": 1.8,
        "probability": 78,
        "message": "BTC 1D BUY called at 61000 (+1.8%) -> CORRECT (P=78%)",
    }
    try:
        _state.add_alert(alert)
    except Exception:
        pass
    try:
        if _store is not None:
            _store.add_alert(alert)
    except Exception:
        pass
    try:
        _notifier.fire(alert)
    except Exception:
        pass
    return {"status": "ok", "alert": alert}


@app.get("/api/crowd")
def crowd():
    if _crowd is None:
        return {"status": "unavailable", "source": "cryptopanic"}
    return _crowd.snapshot()


@app.get("/api/crowd/{symbol}")
def crowd_symbol(symbol: str):
    if _crowd is None:
        raise HTTPException(status_code=503, detail="crowd not bound")
    snap = _crowd.snapshot()
    sym = snap.get("symbols", {}).get(symbol.upper())
    if sym is None:
        raise HTTPException(status_code=404, detail="no crowd data for symbol")
    return sym


@app.post("/api/crowd/token")
def crowd_token(payload: dict = None):
    if _crowd is None:
        raise HTTPException(status_code=503, detail="crowd not bound")
    token = ""
    if isinstance(payload, dict):
        token = payload.get("token") or ""
    _crowd.set_token(token)
    return _crowd.snapshot()


def _event_stream():
    last_ids = set()
    last_crowd_ts = None
    try:
        while True:
            snap_list = _state.all_snapshots() if _state is not None else []
            payload = {"ts": _iso(), "snapshots": snap_list}
            yield "event: snapshot\ndata: " + json.dumps(payload) + "\n\n"

            if _crowd is not None:
                try:
                    cdata = _crowd.snapshot()
                    cts = cdata.get("updated_ts")
                    if cts and cts != last_crowd_ts:
                        last_crowd_ts = cts
                        yield ("event: crowd\ndata: " +
                               json.dumps({"crowd": cdata}) + "\n\n")
                except Exception:
                    pass

            alerts = []
            if _state is not None:
                alerts = _state.recent_alerts(100)
            elif _store is not None:
                alerts = _store.recent_alerts(100)
            fresh = [a for a in alerts if _alert_id(a) not in last_ids]
            if fresh:
                for a in fresh:
                    last_ids.add(_alert_id(a))
                yield ("event: alert\ndata: " + json.dumps({"alerts": fresh}) + "\n\n")

            time.sleep(0)
            yield "event: ping\ndata: " + json.dumps({"ts": _iso()}) + "\n\n"
            time.sleep(5)
    except GeneratorExit:
        pass


@app.get("/api/stream")
def stream():
    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )