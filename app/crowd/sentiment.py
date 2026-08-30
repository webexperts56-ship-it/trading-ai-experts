import json
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

COINS = {
    "BTC": ["bitcoin", "btc"],
    "ETH": ["ethereum", "eth"],
    "SOL": ["solana", "sol"],
    "BNB": ["bnb", "binance coin"],
    "XRP": ["xrp", "ripple"],
    "DOGE": ["dogecoin", "doge"],
}

REDDIT_FEEDS = {
    "BTC": "Bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binance",
    "XRP": "XRP",
    "DOGE": "dogecoin",
}

_BULL_WORDS = [
    "bull", "surge", "soar", "rally", "gain", "up", "rise", "rises", "rising",
    "record", "high", "jump", "climb", "boost", "strong", "buy", "buyer",
    "inflow", "adoption", "breakout", "outperform", "hits", "tops", "long",
    "bullish", "recovery", "green", "support", "milestone",
]
_BEAR_WORDS = [
    "bear", "crash", "drop", "falls", "fell", "sink", "sinks", "plunge",
    "slide", "loss", "loses", "down", "low", "sell", "seller", "outflow",
    "reject", "slump", "correction", "bearish", "red", "resistance", "wipeout",
    "liquidation", "warning", "risk",
]

_FNG_API = "https://api.alternative.me/fng/?limit=1"
_NEWS_API = ("https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en")
_REDDIT_API = ("https://www.reddit.com/r/{sub}/new/.rss?limit={n}")
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")


def _iso():
    return datetime.now(timezone.utc).isoformat()


class CrowdSentiment:
    def __init__(self, config=None):
        self.config = config
        self._lock = threading.Lock()
        self._result = {"updated_ts": None, "symbols": {}, "market": {},
                        "status": "loading", "source": "free"}
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return self
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="crowd")
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def set_token(self, token):
        return self.snapshot()

    def token(self):
        return ""

    def _loop(self):
        while not self._stop.is_set():
            self.refresh()
            self._sleep(self._interval())

    @staticmethod
    def _interval():
        try:
            return float(getattr(CrowdSentiment._cfg(), "crowd_interval", 180.0))
        except Exception:
            return 180.0

    @staticmethod
    def _cfg():
        from config import CONFIG
        return CONFIG

    @staticmethod
    def _sleep(sec):
        end = time.time() + sec
        while time.time() < end:
            time.sleep(0.5)

    def refresh(self):
        fng = self._fetch_fng()
        symbols = {}
        for sym, terms in COINS.items():
            symbols[sym] = self._news_aggregate(sym, terms)
        market = self._market_summary(symbols, fng)
        self._set_result({
            "updated_ts": _iso(),
            "symbols": symbols,
            "market": market,
            "status": "ok",
            "source": "news+reddit",
            "fng": fng,
        })

    def _fetch_fng(self):
        try:
            req = urllib.request.Request(_FNG_API,
                                         headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                doc = json.loads(resp.read())
            item = (doc.get("data") or [{}])[0]
            value = item.get("value")
            classification = item.get("value_classification", "Neutral")
            return {"value": int(value) if value else None,
                    "classification": classification}
        except Exception:
            return {"value": None, "classification": None}

    def _news_aggregate(self, symbol, terms):
        query = " OR ".join(terms)
        headlines = []
        for source, fetcher in (
            ("news", self._fetch_news),
            ("reddit", self._fetch_reddit),
        ):
            try:
                got = fetcher(query, symbol)
                if got:
                    headlines.extend(got)
            except Exception as e:
                print(f"crowd {source} fail", symbol, str(e)[:80])
            if source == "reddit":
                time.sleep(2.0)
        if not headlines:
            return {"symbol": symbol, "status": "error",
                    "detail": "no sources"}
        bull = 0
        bear = 0
        for head in headlines:
            b = self._classify(head)
            if b > 0:
                bull += 1
            elif b < 0:
                bear += 1
        total = bull + bear
        score = round((bull - bear) / float(total), 3) if total else 0.0
        if total == 0:
            bias = "EMPTY"
        elif score >= 0.15:
            bias = "BULLISH"
        elif score <= -0.15:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"
        return {
            "symbol": symbol,
            "posts": len(headlines),
            "bullish_votes": bull,
            "bearish_votes": bear,
            "total_votes": total,
            "score": score,
            "bias": bias,
            "headlines": headlines[:5],
        }

    @staticmethod
    def _fetch_reddit(query, symbol):
        sub = REDDIT_FEEDS.get(symbol)
        if not sub:
            return []
        url = _REDDIT_API.format(sub=sub, n=15)
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", "ignore")
        titles = re.findall(r"<title>([^<]+)</title>", raw)
        titles = [t.strip() for t in titles if t.strip() and "reddit.com" not in t.lower()]
        return titles[:15]

    @staticmethod
    def _fetch_news(query, symbol=None):
        url = _NEWS_API.format(q=urllib.parse.quote(query))
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", "ignore")
        titles = re.findall(r"<title>([^<]+)</title>", raw)
        return [t.strip() for t in titles[1:31]]

    @staticmethod
    def _classify(text):
        low = " " + text.lower() + " "
        bull = sum(1 for w in _BULL_WORDS if (" " + w + " ") in low)
        bear = sum(1 for w in _BEAR_WORDS if (" " + w + " ") in low)
        if bull == bear:
            bull = sum(1 for w in _BULL_WORDS if len(w) > 2 and w in low)
            bear = sum(1 for w in _BEAR_WORDS if len(w) > 2 and w in low)
        if bull > bear:
            return 1
        if bear > bull:
            return -1
        return 0

    @staticmethod
    def _market_summary(symbols, fng):
        voted = [a for a in symbols.values() if a.get("total_votes")]
        total_bull = sum(a.get("bullish_votes", 0) for a in voted)
        total_bear = sum(a.get("bearish_votes", 0) for a in voted)
        total = total_bull + total_bear
        net = round((total_bull - total_bear) / float(total), 3) if total else 0.0
        ranked = sorted(voted, key=lambda a: a.get("total_votes", 0),
                        reverse=True)
        top = ranked[0]["symbol"] if ranked else None
        fng_val = (fng or {}).get("value")
        if fng_val is not None:
            mood = "BULLISH" if fng_val >= 55 else ("BEARISH" if fng_val <= 45 else "NEUTRAL")
        elif net >= 0.1:
            mood = "BULLISH"
        elif net <= -0.1:
            mood = "BEARISH"
        else:
            mood = "NEUTRAL"
        return {
            "total_votes": total,
            "bullish_votes": total_bull,
            "bearish_votes": total_bear,
            "net_score": net,
            "mood": mood,
            "fear_greed": fng_val,
            "fear_greed_label": (fng or {}).get("classification"),
            "top_symbol": top,
            "coins_with_data": len(voted),
        }

    def _set_result(self, result):
        with self._lock:
            self._result = result

    def snapshot(self):
        with self._lock:
            return dict(self._result)

    def score_for(self, symbol):
        snapped = self.snapshot()
        agg = (snapped.get("symbols") or {}).get(symbol)
        if not agg or not agg.get("total_votes"):
            return None
        return agg.get("score")
