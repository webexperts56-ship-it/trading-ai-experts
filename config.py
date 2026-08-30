"""Central configuration for the system. Values come from .env (optional)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv not installed yet
    pass


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Universe:
    """Ticker universe definition. Each entry is a dict passed to the engine."""

    crypto: tuple[str, ...] = tuple(
        s.strip() for s in os.getenv("CRYPTO_SYMBOLS", "BTC,ETH,SOL,BNB,XRP,DOGE").split(",") if s.strip()
    )
    psx: tuple[str, ...] = tuple(
        s.strip()
        for s in os.getenv(
            "PSX_SYMBOLS", "KEL.KA,EFERT.KA,OGDC.KA,MARI.KA,LUCK.KA,HUBC.KA,SYS.KA,MEBL.KA"
        ).split(",")
        if s.strip()
    )

    def all(self) -> list[dict]:
        out: list[dict] = []
        for sym in self.crypto:
            out.append(
                {
                    "symbol": sym,
                    "asset_class": "crypto",
                    "market": "crypto",
                    "provider": "binance",
                }
            )
        for sym in self.psx:
            out.append(
                {
                    "symbol": sym,
                    "asset_class": "equity",
                    "market": "PSX",
                    "provider": "yahoo",
                }
            )
        return out


@dataclass(frozen=True)
class Config:
    universe: Universe = field(default_factory=Universe)

    binance_rest_url: str = os.getenv("BINANCE_REST_URL", "https://api.binance.com")
    binance_ws_url: str = os.getenv("BINANCE_WS_URL", "wss://stream.binance.com:9443")
    psx_api_base: str = os.getenv("PSX_API_BASE", "")

    poll_interval: float = _env_float("POLL_INTERVAL", 10.0)
    analyze_interval: float = _env_float("ANALYZE_INTERVAL", 60.0)
    fundamental_interval: float = _env_float("FUNDAMENTAL_INTERVAL", 1800.0)
    candle_refresh_interval: float = _env_float("CANDLE_REFRESH_INTERVAL", 300.0)

    # How long a metric cache entry stays fresh (seconds)
    cache_ttl: float = _env_float("CACHE_TTL", 15.0)

    alerts_enabled: bool = os.getenv("ALERTS_ENABLED", "true").lower() == "true"
    desktop_alerts: bool = os.getenv("DESKTOP_ALERTS", "true").lower() == "true"
    alert_webhook_url: str = os.getenv("ALERT_WEBHOOK_URL", "")

    # Telegram (blocked in Pakistan, optional elsewhere)
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Free Email notifications (works in Pakistan via Gmail SMTP + app password)
    email_from: str = os.getenv("EMAIL_FROM", "")
    email_to: str = os.getenv("EMAIL_TO", "")
    email_app_password: str = os.getenv("EMAIL_APP_PASSWORD", "")
    email_smtp_host: str = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
    email_smtp_port: int = _env_int("EMAIL_SMTP_PORT", 587)

    cryptopanic_token: str = os.getenv("CRYPTOPANIC_TOKEN", "")
    crowd_interval: float = _env_float("CROWD_INTERVAL", 120.0)

    use_ml: bool = os.getenv("USE_ML", "true").lower() == "true"
    db_path: str = os.getenv("DB_PATH", "data/signals.db")
    models_dir: str = os.getenv("MODELS_DIR", "models")

    auth_username: str = os.getenv("AUTH_USERNAME", "admin")
    auth_password: str = os.getenv("AUTH_PASSWORD", "")

    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = _env_int("PORT", 8000)


CONFIG = Config()