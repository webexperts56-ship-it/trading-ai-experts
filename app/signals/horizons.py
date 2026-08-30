HORIZON_ORDER = ["1MIN", "5MIN", "1H", "6H", "1D"]

BLEND_TIMEFRAMES = ["5m", "15m", "1h", "1d"]

TO_SECONDS = {
    "1MIN": 60,
    "5MIN": 300,
    "1H": 3600,
    "6H": 21600,
    "1D": 86400,
}

HORIZON_CONFIG = [
    {
        "key": "1MIN",
        "label": "1 Minute",
        "seconds": 60,
        "category_weights": {
            "momentum": 0.32,
            "oscillator": 0.26,
            "trend": 0.08,
            "volume": 0.16,
            "candle": 0.12,
            "fundamental": 0.06,
        },
        "tf_blend": {
            "5m": 0.25,
            "15m": 0.45,
            "1h": 0.30,
        },
        "vol_penalty": 0.8,
        "fundamental_weight_active": True,
    },
    {
        "key": "5MIN",
        "label": "5 Minutes",
        "seconds": 300,
        "category_weights": {
            "momentum": 0.30,
            "oscillator": 0.27,
            "trend": 0.10,
            "volume": 0.16,
            "candle": 0.11,
            "fundamental": 0.06,
        },
        "tf_blend": {
            "5m": 0.50,
            "15m": 0.35,
            "1h": 0.15,
        },
        "vol_penalty": 0.8,
        "fundamental_weight_active": True,
    },
    {
        "key": "1H",
        "label": "1 Hour",
        "seconds": 3600,
        "category_weights": {
            "momentum": 0.28,
            "oscillator": 0.26,
            "trend": 0.14,
            "volume": 0.14,
            "candle": 0.10,
            "fundamental": 0.08,
        },
        "tf_blend": {
            "15m": 0.45,
            "1h": 0.40,
            "1d": 0.15,
        },
        "vol_penalty": 0.8,
        "fundamental_weight_active": True,
    },
    {
        "key": "6H",
        "label": "6 Hours",
        "seconds": 21600,
        "category_weights": {
            "momentum": 0.24,
            "oscillator": 0.24,
            "trend": 0.18,
            "volume": 0.13,
            "candle": 0.08,
            "fundamental": 0.13,
        },
        "tf_blend": {
            "15m": 0.30,
            "1h": 0.40,
            "1d": 0.30,
        },
        "vol_penalty": 0.8,
        "fundamental_weight_active": True,
    },
    {
        "key": "1D",
        "label": "1 Day",
        "seconds": 86400,
        "category_weights": {
            "momentum": 0.20,
            "oscillator": 0.20,
            "trend": 0.22,
            "volume": 0.11,
            "candle": 0.06,
            "fundamental": 0.21,
        },
        "tf_blend": {
            "1h": 0.35,
            "1d": 0.65,
        },
        "vol_penalty": 0.8,
        "fundamental_weight_active": True,
    },
]

def horizon_config(key):
    for entry in HORIZON_CONFIG:
        if entry["key"] == key:
            return entry
    return None
