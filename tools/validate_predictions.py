from config import CONFIG

BUCKET_BOUNDS = (
    (0.0, 10.0, "50-60"),
    (10.0, 20.0, "60-70"),
    (20.0, 30.0, "70-80"),
    (30.0, 51.0, "80-100"),
)
BUCKET_ORDER = ("50-60", "60-70", "70-80", "80-100")


def _normalize_prob(probability_up):
    if probability_up is None:
        return None
    p = float(probability_up)
    if p <= 1.0:
        p *= 100.0
    return p


def _bucket(probability_up):
    p = _normalize_prob(probability_up)
    if p is None:
        return None
    d = abs(p - 50.0)
    for lo, hi, name in BUCKET_BOUNDS:
        if lo <= d < hi:
            return name
    return "80-100"


def _print_summary(store):
    summary = store.predictions_summary()
    print("prediction summary:")
    print("  resolved: {}".format(summary.get("resolved")))
    print("  correct:  {}".format(summary.get("correct")))
    print("  hit rate: {}%".format(summary.get("hit_rate")))
    print("  pending:  {}".format(summary.get("pending")))
    by_horizon = summary.get("by_horizon", {})
    print("  per-horizon hit rates:")
    for horizon in sorted(by_horizon):
        entry = by_horizon[horizon]
        print("    {:<5} n={:>5} correct={:>5} hit={:>6.1f}%".format(
            horizon, entry["n"], entry["correct"], entry["hit_rate"]))


def _print_recent(store):
    rows = store.recent_predictions(10)
    print("10 most recent predictions (correct / actual_return):")
    print("{:<8} {:<5} {:<11} {:>7} {:>8} {:>10} {:>12}".format(
        "symbol", "hor", "action", "p_up", "correct", "act_ret%", "issued_ts"))
    for pred in rows:
        correct = pred.get("correct")
        ret = pred.get("actual_return")
        prob = _normalize_prob(pred.get("probability_up"))
        correct_s = "" if correct is None else str(bool(correct))
        ret_s = "" if ret is None else "{:.2f}".format(ret * 100)
        print("{:<8} {:<5} {:<11} {:>6.1f}% {:>8} {:>10} {:>12}".format(
            pred.get("symbol", ""),
            pred.get("horizon", ""),
            pred.get("action", ""),
            prob or 0.0,
            correct_s,
            ret_s,
            pred.get("issued_ts") or ""))


def _bucket_stats(rows):
    buckets = {}
    for pred in rows:
        if pred.get("correct") is None:
            continue
        bucket = _bucket(pred.get("probability_up"))
        if bucket is None:
            continue
        entry = buckets.setdefault(bucket, {"n": 0, "correct": 0})
        entry["n"] += 1
        if pred["correct"]:
            entry["correct"] += 1
    return buckets


def _print_buckets(rows):
    buckets = _bucket_stats(rows)
    print("hit rate by confidence bucket (|p_up - 50|):")
    print("{:<8} {:>8} {:>8} {:>10}".format("bucket", "n", "correct", "hit%"))
    for name in BUCKET_ORDER:
        entry = buckets.get(name, {"n": 0, "correct": 0})
        hit = (
            100.0 * entry["correct"] / entry["n"] if entry["n"] else 0.0
        )
        print("{:<8} {:>8} {:>8} {:>9.1f}%".format(
            name, entry["n"], entry["correct"], hit))


def main():
    from app.store.history import Store

    store = Store(CONFIG.db_path)
    print("db: {}".format(CONFIG.db_path))
    _print_summary(store)
    print()
    _print_recent(store)
    print()
    rows = store.recent_predictions(5000)
    _print_buckets(rows)


if __name__ == "__main__":
    main()