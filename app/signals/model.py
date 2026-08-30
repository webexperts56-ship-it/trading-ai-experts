import os

FEATURE_KEYS = [
    "rsi",
    "macd_hist_norm",
    "stoch_k",
    "atr_pct",
    "adx",
    "cmf",
    "vwap_z",
    "vol_ratio",
    "bb_position",
    "roc5",
    "roc10",
    "roc20",
    "ema_gap_20_50",
    "ema_gap_50_200",
    "close_sma200_gap",
    "realized_vol",
    "vol_norm_mom",
    "hl_range_pct",
]


def train_and_save(feature_records, targets, keys, horizon, out_dir):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    import joblib

    if len(feature_records) == 0 or len(feature_records) != len(targets):
        raise ValueError("feature_records and targets must be non-empty and equal length")

    X = [[rec.get(k, 0.0) for k in keys] for rec in feature_records]
    y = list(targets)
    n = len(X)

    if n < 300:
        cal_frac = 0.3
    else:
        cal_frac = 0.22
    split = int(n * (1.0 - cal_frac))

    X_train = X[:split]
    y_train = y[:split]
    X_cal = X[split:]
    y_cal = y[split:]

    def make_model(seed):
        return Pipeline([
            ("scaler", StandardScaler()),
            ("clf", HistGradientBoostingClassifier(
                max_iter=180,
                min_samples_leaf=25,
                learning_rate=0.08,
                random_state=seed,
            )),
        ])

    base = [make_model(seed) for seed in range(6)]
    for model in base:
        model.fit(X_train, y_train)

    cal_probs = _ensemble_proba(base, X_cal)
    clipped = [min(max(p, 5e-3), 1.0 - 5e-3) for p in cal_probs]
    calibrated = _fit_platt(clipped, y_cal)

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, horizon + ".pkl")
    joblib.dump({"keys": keys, "base": base, "cal": calibrated}, path)

    up = sum(1 for t in y if t == 1)
    down = sum(1 for t in y if t == 0)
    return {"samples": len(y), "up": up, "down": down, "calibration": "platt", "seeds": 6}


def _ensemble_proba(base, X):
    from statistics import mean
    probs = []
    for model in base:
        probs.append(model.predict_proba(X)[:, 1])
    return [mean(row) for row in zip(*probs)]


def load_models(models_dir):
    if not models_dir or not os.path.isdir(models_dir):
        return {}
    models = {}
    for horizon in ["1MIN", "5MIN", "1H", "6H", "1D", "5D", "1MO"]:
        path = os.path.join(models_dir, horizon + ".pkl")
        if not os.path.isfile(path):
            continue
        try:
            import joblib
            models[horizon] = joblib.load(path)
        except Exception:
            try:
                import pickle
                with open(path, "rb") as fh:
                    models[horizon] = pickle.load(fh)
            except Exception:
                continue
    return models


def _fit_platt(probs, y_cal):
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    arr = np.asarray(probs, dtype=float)
    if arr.size < 20 or np.unique(arr).size < 2 or np.std(arr) < 1e-9:
        return None
    try:
        model = LogisticRegression(C=1.0, max_iter=200)
        model.fit(arr.reshape(-1, 1), y_cal)
        return model
    except Exception:
        return None


def _is_sklearn_pipeline(model):
    return callable(getattr(model, "predict_proba", None)) and hasattr(model, "classes_")


def predict(model, feature_vec):
    if model is None or not feature_vec:
        return None
    try:
        keys = model.get("keys", FEATURE_KEYS) if isinstance(model, dict) else FEATURE_KEYS
        if isinstance(model, dict) and "base" in model:
            base = model["base"]
            cal = model.get("cal")
        elif _is_sklearn_pipeline(model):
            base = [model]
            cal = None
        else:
            return None

        ordered = [feature_vec.get(k, 0.0) for k in keys]
        base_probs = []
        for model_i in base:
            proba = model_i.predict_proba([ordered])[0]
            classes = list(model_i.classes_)
            if 1 in classes:
                base_probs.append(float(proba[classes.index(1)]))
            elif len(classes) == 2:
                base_probs.append(float(proba[1]))
            else:
                return None
        p = sum(base_probs) / len(base_probs)
        if cal is not None:
            p = min(max(p, 1e-6), 1.0 - 1e-6)
            p = float(cal.predict_proba([[p]])[0][1])
        return float(p)
    except Exception:
        return None
