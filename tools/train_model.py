from datetime import datetime, timezone

from config import CONFIG

HORIZON_BARS = {
    "1D": 1,
    "5D": 5,
    "1MO": 21,
}
MIN_SAMPLES = 300
MIN_BARS = 250
FIRST_BAR = 120
BAR_TAIL = 22


def daily_frame(meta):
    from app.data.binance import binance_provider
    from app.data.psx import psx_provider

    if meta["asset_class"] == "crypto":
        return binance_provider.klines(meta["symbol"], "1d", 600)
    return psx_provider.get_candles(meta["symbol"], "1d", 600)


def collect_samples():
    from app.technical.features import ml_feature_vector

    by_horizon = {h: [] for h in HORIZON_BARS}
    for meta in CONFIG.universe.all():
        symbol = meta["symbol"]
        try:
            daily = daily_frame(meta)
            if daily is None or len(daily) < MIN_BARS:
                n_bars = 0 if daily is None else len(daily)
                print("train: skip {} insufficient data ({} bars)".format(
                    symbol, n_bars))
                continue
            closes = daily["close"]
            for i in range(FIRST_BAR, len(daily) - BAR_TAIL):
                window = daily.iloc[:i + 1]
                feats = ml_feature_vector(window)
                for horizon, bars_ahead in HORIZON_BARS.items():
                    if i + bars_ahead >= len(daily):
                        continue
                    label = (
                        1 if closes.iloc[i + bars_ahead] > closes.iloc[i]
                        else 0
                    )
                    by_horizon[horizon].append((feats, label))
        except Exception as exc:
            print("train: symbol {} failed: {}".format(symbol, exc))
    return by_horizon


def train_horizons(by_horizon):
    from app.signals.model import train_and_save

    summary = {}
    for horizon, samples in by_horizon.items():
        if len(samples) < MIN_SAMPLES:
            summary[horizon] = {"status": "skipped", "samples": len(samples)}
            continue
        records = [s[0] for s in samples]
        targets = [s[1] for s in samples]
        keys = list(records[0].keys())
        res = train_and_save(records, targets, keys, horizon,
                             CONFIG.models_dir)
        summary[horizon] = {
            "status": "trained",
            "samples": res.get("samples", len(samples)),
            "up": res.get("up"),
            "down": res.get("down"),
        }
    return summary


def main():
    ts = datetime.now(timezone.utc).isoformat()
    print("train_model run started at {} (UTC)".format(ts))
    by_horizon = collect_samples()
    print("collected samples: {}".format(
        {h: len(samples) for h, samples in by_horizon.items()}))
    summary = train_horizons(by_horizon)
    print("training summary:")
    for horizon, info in sorted(summary.items()):
        if info["status"] == "skipped":
            print("  {}: skipped ({} samples)".format(horizon, info["samples"]))
        else:
            print("  {}: trained ({} samples, up={}, down={})".format(
                horizon, info["samples"], info["up"], info["down"]))


if __name__ == "__main__":
    main()