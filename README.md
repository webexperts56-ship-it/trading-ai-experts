---
title: Trading AI Experts
emoji: 📈
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
pinned: false
---

# Trading AI Experts

Real-time multi-dimensional equity & crypto evaluation system. It fuses
**fundamental**, **technical**, and **trend** analysis into actionable
directional signals across **7 forecast horizons** — and alerts you live when a
prediction proves correct.

| Horizon | Key | Source data used | Primary weighting |
|---|---|---|---|
| 1 min | `1MIN` | 5m/15m/1h candles | momentum + oscillators + volume |
| 5 min | `5MIN` | 5m/15m/1h candles | momentum + oscillators + volume |
| 1 hour | `1H` | 15m/1h/1d candles | momentum + oscillators + trend |
| 6 hours | `6H` | 15m/1h/1d candles | momentum + oscillators + trend |
| 1 day | `1D` | 1h/1d candles | momentum + trend + fundamentals |
| 5 days | `5D` | 1h/1d candles | trend + fundamentals |
| 1 month | `1MO` | 1d candles | fundamentals + trend |

## Architecture

```
run.py                      entrypoint: starts engine + web server
config.py                   configuration (.env overrides)
app/
  data/      live feeds: Binance (crypto, real-time WS), Yahoo (PSX + fundamentals),
             PSX provider (falls back to Yahoo). CandleStore per symbol/timeframe.
  fundamentals/  ratio extraction + financial-health / valuation scoring (-100..+100)
  technical/  indicator library (RSI, MACD, Bollinger, Stoch, ATR, ADX, OBV, CMF,
             VWAP, ...) and normalized feature sub-scores
  trend/     market regime detection (BULL/BEAR/SIDEWAYS) + market-wide context
  signals/   multi-horizon aggregation engine (weighted, volatility-aware),
             6-seed gradient-boosted ensemble + Platt calibration for ML probabilities
  rtfeed/    real-time polling + scheduler threads; shared snapshot state
  alert/     prediction lifecycle monitor + desktop/webhook notification
  web/       FastAPI + SSE dashboard (dark terminal UI, no dependencies)
  store/     SQLite history of snapshots, predictions, alerts (WAL)
tools/
  train_model.py          train + save per-horizon direction models
  backtest.py             chronological, embargoed out-of-sample evaluation
  validate_predictions.py score live logged predictions vs reality
docs/research_findings.md research-backed algorithm recommendations (applied)
```

Every ticker produces a `Snapshot`: quote + fundamentals + technicals + trend +
one `HorizonSignal` per horizon. Each signal carries a **score** (-100..+100), a
**direction** (STRONG BUY→STRONG SELL), a **probability up**, and **confidence**.
The ML models (when trained) fuse into the daily/longer horizons; minutely/hourly
signals stay heuristic (research shows minutely ML adds little at this data size).

## Setup

```bash
cd "Trading AI Experts"
python3 -m pip install -r requirements.txt
cp .env.example .env        # optional; defaults work out of the box
python3 -m tools.train_model   # (optional) train ML direction models on real data
python3 run.py
# open http://127.0.0.1:8000
```

No API keys required. Crypto is streamed from **Binance** (free websocket; override
base URLs in `.env` if geo-blocked). Pakistan Stock Exchange symbols use Yahoo's
`.KA` suffix (e.g. `KEL.KA`, `EFERT.KA`) — edit `PSX_SYMBOLS` in `.env` to taste.

## Alerts & notifications

Every directional prediction is logged. When its window expires the system
compares predicted vs actual move and raises an alert:

- **Desktop notification** (macOS via `osascript`) — `DESKTOP_ALERTS=true`
- **Webhook** (Discord/Slack/Telegram) — set `ALERT_WEBHOOK_URL`
- **In-app** — live alert panel in the dashboard (SSE push)

Alert kinds: `PREDICTION_SUCCESS` (correct), `PREDICTION_WRONG` (wrong &
significant/strongly confident), `PREDICTION_MISS` (moved too little to judge).

## CLI tools

```bash
python3 -m tools.backtest    # honest out-of-sample hit-rates + net signal quality
python3 -m tools.validate_predictions  # how live predictions are scoring
```

`backtest` uses a chronological 70/30 split with a 5-bar embargo and reports
per-horizon hit rates; treat any result above ~55% hit-rate / 58% accuracy as
good — the research notes this is roughly the edge real signal systems deliver.

## Evaluation engine notes

- Fundamentals (PSX) come from Yahoo; free feeds carry few statement fields, so
  `fundamental_score` falls back gracefully when data is thin.
- `1MIN`/`5MIN` need the crypto websocket live; PSX intraday is Yahoo-delayed
  (PSX does not publish a free streaming feed).
- Prices are best-effort — always verify before acting on a signal. This is a
  research/decision-support tool, not financial advice.