from config import CONFIG

HORIZON_BARS = {
    "1D": 1,
    "5D": 5,
    "1MO": 21,
}
BUY_ACTIONS = ("BUY", "STRONG_BUY")
SELL_ACTIONS = ("SELL", "STRONG_SELL")
MIN_BARS = 250
TRAIN_FRACTION = 0.70
EMBARGO_BARS = 5


def daily_frame(meta):
    from app.data.binance import binance_provider
    from app.data.psx import psx_provider

    if meta["asset_class"] == "crypto":
        return binance_provider.klines(meta["symbol"], "1d", 600)
    return psx_provider.get_candles(meta["symbol"], "1d", 600)


def meta_for(item):
    name = (
        item["symbol"].split(".")[0] if item["market"] == "PSX"
        else item["symbol"]
    )
    return {
        "symbol": item["symbol"],
        "name": name,
        "asset_class": item["asset_class"],
        "market": item["market"],
        "provider": item["provider"],
    }


def _signals_of(snap):
    if hasattr(snap, "signals"):
        return list(snap.signals)
    return list(snap.get("signals", []) or [])


def _horizon(sig):
    if isinstance(sig, dict):
        return sig.get("horizon")
    return getattr(sig, "horizon", None)


def _action(sig):
    if sig is None:
        return None
    if isinstance(sig, dict):
        return sig.get("action")
    return getattr(sig, "action", None)


def new_stats():
    return {
        "n": 0,
        "correct": 0,
        "return_correct": 0.0,
        "return_wrong": 0.0,
        "abs_move": 0.0,
        "up_return": 0.0,
        "up_cnt": 0,
        "down_return": 0.0,
        "down_cnt": 0,
    }


def evaluate_symbol(meta, aggregate):
    from app.signals.engine import analyze_daily_only

    symbol = meta["symbol"]
    per_horizon = {h: new_stats() for h in HORIZON_BARS}
    try:
        daily = daily_frame(meta)
        if daily is None or len(daily) < MIN_BARS:
            n_bars = 0 if daily is None else len(daily)
            print("backtest: skip {} insufficient data ({} bars)".format(
                symbol, n_bars))
            return None
        closes = daily["close"]
        n_bars = len(daily)
        train_count = int(n_bars * TRAIN_FRACTION)
        first_test_bar = train_count + EMBARGO_BARS - 1
        if first_test_bar >= n_bars:
            print("backtest: skip {} test zone empty".format(symbol))
            return None
        for i in range(first_test_bar, n_bars):
            window = daily.iloc[:i + 1]
            try:
                snap = analyze_daily_only(meta, window, fundamental=None,
                                          models={})
            except Exception as exc:
                print("backtest: analyze failed {} bar {}: {}".format(
                    symbol, i, exc))
                continue
            by_horizon = {}
            for sig in _signals_of(snap):
                key = _horizon(sig)
                if key in HORIZON_BARS:
                    by_horizon[key] = sig
            close = float(closes.iloc[i])
            for horizon, bars_ahead in HORIZON_BARS.items():
                sig = by_horizon.get(horizon)
                action = _action(sig)
                if action not in BUY_ACTIONS and action not in SELL_ACTIONS:
                    continue
                up = action in BUY_ACTIONS
                idx_fwd = min(i + bars_ahead, n_bars - 1)
                actual = float(closes.iloc[idx_fwd])
                actual_return = (actual - close) / close if close else 0.0
                correct = (up and actual > close) or (not up and actual < close)
                row = per_horizon[horizon]
                row["n"] += 1
                row["abs_move"] += abs(actual_return)
                if correct:
                    row["correct"] += 1
                    row["return_correct"] += actual_return
                else:
                    row["return_wrong"] += actual_return
                if up:
                    row["up_cnt"] += 1
                    row["up_return"] += actual_return
                else:
                    row["down_cnt"] += 1
                    row["down_return"] += actual_return
        for horizon, row in per_horizon.items():
            aggregate[horizon] = {
                k: aggregate[horizon][k] + row[k] for k in row
            }
    except Exception as exc:
        print("backtest: symbol {} failed: {}".format(symbol, exc))
        return None
    return per_horizon


def summarize_row(row):
    n = row["n"]
    correct = row["correct"]
    hit = 100.0 * correct / n if n else 0.0
    avg_correct = (
        row["return_correct"] / correct if correct else 0.0
    )
    wrong_n = n - correct
    avg_wrong = row["return_wrong"] / wrong_n if wrong_n else 0.0
    avg_abs = row["abs_move"] / n if n else 0.0
    up_avg = row["up_return"] / row["up_cnt"] if row["up_cnt"] else 0.0
    down_avg = row["down_return"] / row["down_cnt"] if row["down_cnt"] else 0.0
    net = up_avg - down_avg
    return n, hit, avg_correct, avg_wrong, avg_abs, net


def print_table(title, rows):
    print("=" * 80)
    print(title)
    print("=" * 80)
    print("{:<10} {:<6} {:>6} {:>7} {:>11} {:>11} {:>9} {:>9}".format(
        "symbol", "hor", "n", "hit%", "ret_ok%", "ret_bad%", "abs%", "net%"))
    print("-" * 80)
    for symbol, horizon, row in rows:
        n, hit, avg_ok, avg_bad, avg_abs, net = summarize_row(row)
        print("{:<10} {:<6} {:>6} {:>6.1f}% {:>10.2f}% {:>10.2f}% "
              "{:>8.2f}% {:>8.2f}%".format(
                  symbol, horizon, n, hit,
                  avg_ok * 100, avg_bad * 100, avg_abs * 100, net * 100))
    print("-" * 80)


def main():
    aggregate = {h: new_stats() for h in HORIZON_BARS}
    symbol_tables = []
    for item in CONFIG.universe.all():
        meta = meta_for(item)
        per_horizon = evaluate_symbol(meta, aggregate)
        if per_horizon is not None:
            symbol_tables.append((meta["symbol"], per_horizon))

    for symbol, per_horizon in symbol_tables:
        rows = [(symbol, h, per_horizon[h]) for h in HORIZON_BARS]
        print_table("Out-of-sample backtest: {}".format(symbol), rows)

    agg_rows = [("ALL", h, aggregate[h]) for h in HORIZON_BARS]
    print_table("Aggregate (all symbols)", agg_rows)

    for horizon in HORIZON_BARS:
        net = summarize_row(aggregate[horizon])[5]
        print("net signal quality {}: {:.4f} (avg up-return minus "
              "avg down-return; > 0 means skill)".format(horizon, net))

    print()
    print("Honest note: intraday horizons (1MIN/5MIN/1H/6H) are excluded; "
          "1D/5D/1MO are daily-approximated, so these results are "
          "indicative, not a live-accurate backtest.")


if __name__ == "__main__":
    main()