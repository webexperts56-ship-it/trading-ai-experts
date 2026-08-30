import threading
import time
from datetime import datetime, timezone


class RTEngine:
    def __init__(self, config):
        from app.snapshot import SharedState
        from app.store.history import Store
        from app.signals.model import load_models

        self.config = config
        self.state = SharedState()
        self.store = Store(config.db_path)
        self.models = load_models(config.models_dir) if config.use_ml else {}
        self.crowd = None
        from app.analysis.consensus import SignalConsensus
        self.consensus = SignalConsensus()
        self._latest_price = {}
        self._price_lock = threading.Lock()
        self._stop = threading.Event()
        self._last_fund_pull = {}
        self._threads = []
        self._stocks = {}
        self._monitor = None

    def meta(self):
        result = []
        for item in self.config.universe.all():
            symbol = item["symbol"]
            asset_class = item["asset_class"]
            market = item["market"]
            provider = item["provider"]
            name = symbol
            if market == "PSX":
                name = symbol.split(".")[0]
            if not name:
                name = symbol
            result.append({
                "symbol": symbol,
                "name": name,
                "asset_class": asset_class,
                "market": market,
                "provider": provider,
            })
        return result

    def start(self):
        from app.data.base import CandleStore
        from app.data.binance import binance_provider
        from app.data.psx import psx_provider
        from app.data.yahoo import yahoo_provider
        from app.alert.predictions import PredictionMonitor
        from app.alert.notifier import notifier
        from app.crowd.sentiment import CrowdSentiment

        meta_list = self.meta()
        for m in meta_list:
            store = CandleStore(m["symbol"])
            provider = m["provider"]
            if provider == "binance":
                for tf in store.timeframes:
                    df = binance_provider.klines(m["symbol"], tf, 500)
                    store.set_frame(tf, df)
                binance_provider.start_ws([m["symbol"]], store)
            elif provider == "psx":
                for tf in store.timeframes:
                    df = psx_provider.get_candles(m["symbol"], tf, 500)
                    store.set_frame(tf, df)
            self._stocks[m["symbol"]] = store

        for m in meta_list:
            if m["asset_class"] == "equity" and m["provider"] != "binance":
                try:
                    yahoo_provider.get_fundamentals(m["symbol"], m["asset_class"])
                except Exception as e:
                    print("fundamentals warm failed", m["symbol"], e)

        def price_getter(symbol):
            snap = self.state.get_snapshot(symbol)
            if snap and snap.get("quote") and snap["quote"].get("price"):
                return snap["quote"]["price"]
            with self._price_lock:
                return self._latest_price.get(symbol)

        self._monitor = PredictionMonitor(
            self.state, self.store, price_getter, notifier.fire
        )
        self.crowd = CrowdSentiment(self.config).start()

        self._threads.append(threading.Thread(
            target=self._poll_loop, daemon=True, name="poll"
        ))
        self._threads.append(threading.Thread(
            target=self._analyze_loop, daemon=True, name="analyze"
        ))
        self._threads.append(threading.Thread(
            target=self._monitor_loop, daemon=True, name="monitor"
        ))
        self._threads.append(threading.Thread(
            target=self._candle_refresh_loop, daemon=True, name="candle_refresh"
        ))
        for t in self._threads:
            t.start()
        return self

    def _poll_loop(self):
        while not self._stop.is_set():
            started = time.time()
            for m in self.meta():
                try:
                    quote = self._quote_for(m)
                    if quote and quote.price:
                        self._set_price(m["symbol"], quote.price)
                        self._fold_quote_into_store(m["symbol"], quote.price)
                except Exception as e:
                    print("poll failed", m["symbol"], e)
            self._sleep_until(next_step=started + self.config.poll_interval)

    def _analyze_loop(self):
        first = True
        while not self._stop.is_set():
            started = time.time()
            try:
                meta_list = self.meta()
                market_ctx = self._build_market_ctx(meta_list)
                for m in meta_list:
                    try:
                        self._analyze_symbol(m, market_ctx)
                    except Exception as e:
                        print("analyze failed", m["symbol"], e)
                self.state.set_market_ctx(market_ctx)
                try:
                    self.consensus.update(self.state.all_snapshots())
                except Exception as e:
                    print("consensus failed", e)
            except Exception as e:
                print("analyze loop failed", e)
            if first:
                first = False
                continue
            self._sleep_until(next_step=started + self.config.analyze_interval)

    def _analyze_symbol(self, meta, market_ctx):
        from app.fundamentals.scorer import compute_fundamentals
        from app.data.binance import binance_provider

        symbol = meta["symbol"]
        store = self._stocks.get(symbol)
        if store is None:
            print("analyze skipped, no store for", symbol)
            return
        quote = self._quote_for(meta)
        fundamental = self._fundamental_for(meta)
        if fundamental is not None:
            compute_fundamentals(fundamental)
        snap = analyze(meta, store, quote, fundamental, market_ctx, self.models)
        snap_dict = snap.to_dict()
        if not snap_dict["quote"].get("price"):
            daily_close = store.latest("1d")
            if daily_close:
                snap_dict["quote"]["price"] = daily_close["close"]
            else:
                with self._price_lock:
                    latest = self._latest_price.get(symbol)
                if latest:
                    snap_dict["quote"]["price"] = latest
        self.state.put_snapshot(snap_dict)
        try:
            self.store.save_snapshot(snap_dict)
        except Exception as e:
            print("save_snapshot failed", symbol, e)
        if self._monitor:
            self._monitor.ingest(snap_dict)

    def _candle_refresh_loop(self):
        from app.data.binance import binance_provider
        from app.data.psx import psx_provider

        while not self._stop.is_set():
            started = time.time()
            for m in self.meta():
                try:
                    store = self._stocks[m["symbol"]]
                    provider = m["provider"]
                    for tf in ("1h", "4h", "1d"):
                        if provider == "binance":
                            df = binance_provider.klines(m["symbol"], tf, 500)
                        else:
                            df = psx_provider.get_candles(m["symbol"], tf, 500)
                        store.set_frame(tf, df)
                except Exception as e:
                    print("candle refresh failed", m["symbol"], e)
            self._sleep_until(next_step=started + self.config.candle_refresh_interval)

    def _monitor_loop(self):
        failures = 0
        while not self._stop.is_set():
            try:
                self._monitor.run_loop(interval=8.0)
                failures = 0
            except Exception as e:
                failures += 1
                print("monitor failed", e)
            if self._stop.is_set():
                break
            if failures > 1:
                time.sleep(1)

    def stop(self):
        self._stop.set()
        if self.crowd is not None:
            self.crowd.stop()
        for t in self._threads:
            t.join(timeout=2.0)

    def _quote_for(self, meta):
        from app.data.binance import binance_provider
        from app.data.psx import psx_provider
        from app.data.yahoo import yahoo_provider

        provider = meta["provider"]
        symbol = meta["symbol"]
        asset_class = meta["asset_class"]
        quote = None
        try:
            if provider == "binance":
                quote = binance_provider.get_quote(symbol)
            else:
                quote = psx_provider.get_quote(symbol)
                if not self._quote_price(quote):
                    quote = yahoo_provider.get_quote(symbol, asset_class)
            if not self._quote_price(quote):
                quote = None
        except Exception:
            quote = None
        if quote is None:
            return self._stale_quote(symbol)
        return quote

    @staticmethod
    def _quote_price(quote):
        if quote is None:
            return None
        try:
            price = getattr(quote, "price", None)
        except Exception:
            return None
        if price in (None, 0):
            return None
        return price

    def _stale_quote(self, symbol):
        from app.data.base import Quote, utcnow

        with self._price_lock:
            price = self._latest_price.get(symbol)
        if price in (None, 0):
            return None
        try:
            return Quote(
                symbol=symbol,
                price=float(price),
                ts=utcnow(),
                source="stale",
            )
        except Exception:
            return None

    def _fundamental_for(self, meta):
        from app.data.yahoo import yahoo_provider

        symbol = meta["symbol"]
        if meta["asset_class"] != "equity":
            return None
        now = time.time()
        last = self._last_fund_pull.get(symbol)
        if last is None or now - last > self.config.fundamental_interval:
            fd = yahoo_provider.get_fundamentals(symbol, meta["asset_class"])
            self._last_fund_pull[symbol] = now
            return fd
        return None

    def _build_market_ctx(self, meta_list):
        from app.trend.regime import market_context

        momentum_map = {}
        for m in meta_list:
            symbol = m["symbol"]
            snap = self.state.get_snapshot(symbol)
            change = None
            if snap:
                tech = snap.get("technical", {}).get("1d", {}).get("stats", {})
                change = tech.get("change_1d_pct")
                if change is None:
                    quote = snap.get("quote", {})
                    change = quote.get("change_1d_pct")
            if change is None:
                quote = self._quote_for(m)
                if quote:
                    change = getattr(quote, "change_1d_pct", None)
            momentum_map[symbol] = change
        return market_context(momentum_map)

    def _set_price(self, symbol, price):
        with self._price_lock:
            self._latest_price[symbol] = price

    def _fold_quote_into_store(self, symbol, price):
        from app.data.base import utcnow

        provider = None
        for m in self.config.universe.all():
            if m["symbol"] == symbol:
                provider = m["provider"]
                break
        if provider == "binance":
            return
        try:
            ts = utcnow().replace(second=0, microsecond=0)
            self._stocks[symbol].update("1m", {
                "ts": ts,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 0,
            })
        except Exception:
            return None

    def _sleep_until(self, next_step):
        remaining = next_step - time.time()
        while remaining > 0 and not self._stop.is_set():
            sleep_for = min(remaining, 0.25)
            time.sleep(sleep_for)
            remaining = next_step - time.time()


from app.signals.engine import analyze
