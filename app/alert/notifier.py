import subprocess
import threading
import urllib.parse

try:
    from config import CONFIG
except Exception:
    CONFIG = None

_NOTIFY_TYPE_SOUND = {
    "BUY": "Glass",
    "SELL": "Glass",
    "STRONG_BUY": "Basso",
    "STRONG_SELL": "Basso",
    "TAKE_PROFIT": "Ping",
    "STOP_LOSS": "Sosumi",
    "CORRECT": "Glass",
    "WRONG": "Sosumi",
    "MISS": "Ping",
    "SIGNAL": "Glass",
}
_DESKTOP_SCRIPT = [
    "osascript", "-e",
    'display notification "MSG" with title "TITLE" sound name "SOUND"',
]


class Notifier:
    def __init__(self, config=None):
        self.config = config if config is not None else CONFIG

    def fire(self, alert: dict):
        if not self._enabled():
            return
        message = alert.get("message") or alert.get("text") or ""
        if not message:
            return
        ntype = alert.get("type") or alert.get("kind") or "SIGNAL"
        title = alert.get("notification_title") or self._default_title(ntype)
        if self._desktop_enabled():
            t = threading.Thread(target=self._notify_desktop,
                                 args=(title, message, ntype),
                                 daemon=True)
            t.start()
        if self._webhook_url():
            t = threading.Thread(target=self._notify_webhook,
                                 args=(title, message, ntype),
                                 daemon=True)
            t.start()
        if self._telegram_configured():
            t = threading.Thread(target=self._notify_telegram,
                                 args=(title, message, ntype),
                                 daemon=True)
            t.start()
        if self._email_configured():
            t = threading.Thread(target=self._notify_email,
                                 args=(title, message, ntype),
                                 daemon=True)
            t.start()

    @staticmethod
    def _default_title(ntype):
        label = {
            "BUY": "BUY SIGNAL",
            "SELL": "SELL SIGNAL",
            "TAKE_PROFIT": "TARGET COMPLETE",
            "STOP_LOSS": "STOP LOSS HIT",
            "CORRECT": "PREDICTION CORRECT",
            "WRONG": "PREDICTION WRONG",
            "MISS": "NO MOVEMENT",
        }.get(ntype, "TRADING SIGNAL")
        return f"Trading AI : {label}"

    def _enabled(self) -> bool:
        try:
            return bool(self.config.alerts_enabled)
        except Exception:
            return False

    def _desktop_enabled(self) -> bool:
        try:
            return bool(self.config.desktop_alerts)
        except Exception:
            return False

    def _webhook_url(self):
        try:
            return getattr(self.config, "alert_webhook_url", "") or ""
        except Exception:
            return ""
    def _telegram_configured(self):
        try:
            return bool(getattr(self.config, "telegram_bot_token", "") and getattr(self.config, "telegram_chat_id", ""))
        except Exception:
            return False

    def _notify_telegram(self, title: str, message: str, ntype: str):
        import urllib.request, urllib.parse
        token = getattr(self.config, "telegram_bot_token", "")
        chat_id = getattr(self.config, "telegram_chat_id", "")
        text = f"{title}\n{message}"
        url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={urllib.parse.quote(text[:4096])}&parse_mode=HTML"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "TradingAI/1.0"})
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass

    def _email_configured(self) -> bool:
        try:
            return bool(getattr(self.config, "email_from", "") and getattr(self.config, "email_to", "") and getattr(self.config, "email_app_password", ""))
        except Exception:
            return False

    def _notify_email(self, title: str, message: str, ntype: str):
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            frm = getattr(self.config, "email_from", "")
            to = getattr(self.config, "email_to", "")
            pwd = getattr(self.config, "email_app_password", "")
            host = getattr(self.config, "email_smtp_host", "smtp.gmail.com")
            port = int(getattr(self.config, "email_smtp_port", 587))

            msg = MIMEMultipart("alternative")
            msg["Subject"] = title
            msg["From"] = frm
            msg["To"] = to
            html = (
                f"<div style='font-family:Arial,sans-serif;padding:16px'>"
                f"<h2 style='color:#111'>{title}</h2>"
                f"<p style='font-size:15px;white-space:pre-wrap'>{message}</p>"
                f"<hr><small>Trading AI Experts</small></div>"
            )
            msg.attach(MIMEText(html, "html"))

            server = smtplib.SMTP(host, port)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(frm, pwd)
            server.sendmail(frm, [to], msg.as_string())
            server.quit()
        except Exception:
            return

    def _notify_desktop(self, title: str, message: str, ntype: str):
        try:
            sound = _NOTIFY_TYPE_SOUND.get(ntype, "Glass")
            args = [p for p in _DESKTOP_SCRIPT]
            built = []
            for part in args:
                part = part.replace("MSG", message.replace('"', "\\\""))
                part = part.replace("TITLE", title.replace('"', "\\\""))
                part = part.replace("SOUND", sound)
                built.append(part)
            subprocess.Popen(built)
        except Exception:
            return

    def _notify_webhook(self, title: str, message: str, ntype: str):
        try:
            import requests

            requests.post(self._webhook_url(),
                          json={"text": f"[{title}] {message}"}, timeout=5)
        except Exception:
            return


notifier = Notifier()
