window.TA = window.TA || {};

TA.detail = {
  HORIZON_ORDER: ["1MIN", "5MIN", "1H", "6H", "1D"],

  renderDetail(symbol) {
    const snap = TA.state.snapshots.get(symbol);
    if (!snap) return;
    const drawer = document.getElementById("detail-drawer");
    if (!drawer) return;
    const backdrop = document.getElementById("detail-backdrop");

    drawer.classList.remove("hidden");
    drawer.classList.add("open");
    if (backdrop) backdrop.classList.remove("hidden");
    drawer.innerHTML = "";

    drawer.appendChild(this._head(snap));

    const body = TA.utils.el("div", "drawer-body");
    const fund = snap.fundamental || {};
    const trend = snap.trend || {};
    const technical = snap.technical || {};
    const quote = snap.quote || {};

    body.appendChild(this._hero(snap));
    body.appendChild(this._section("Fundamentals", this._fundSection(fund)));
    body.appendChild(this._section("Trend", this._trendSection(trend)));

    const signals = this._signalsSection(snap.signals);
    if (signals) body.appendChild(signals);

    const tech = this._techSection(technical, trend);
    if (tech) body.appendChild(tech);

    body.appendChild(this._section("Quote Stats", this._quoteStats(quote)));

    drawer.appendChild(body);
  },

  _section(title, content) {
    const sec = TA.utils.el("div", "drawer-section");
    sec.appendChild(TA.utils.el("div", "d-label", this.esc(title)));
    if (content) sec.appendChild(content);
    return sec;
  },

  _metric(label, node) {
    const row = TA.utils.el("div", "metric-row");
    row.appendChild(TA.utils.el("span", "metric-label", this.esc(label)));
    const val = TA.utils.el("div", "metric-value");
    val.appendChild(node);
    row.appendChild(val);
    return row;
  },

  _head(snap) {
    const head = TA.utils.el("div", "drawer-head");
    const left = TA.utils.el("div", "d-title");
    left.appendChild(TA.utils.el("strong", "d-symbol", this.esc(snap.symbol || "—")));
    const sub = TA.utils.el("div", "d-sub");
    sub.appendChild(TA.utils.el("span", "d-name", this.esc(snap.name || "—")));
    if (snap.provider) sub.appendChild(TA.utils.pill(this.esc(snap.provider), "pill-muted"));
    if (snap.asset_class) sub.appendChild(TA.utils.pill(this.esc(snap.asset_class), "pill-muted"));
    if (snap.market) sub.appendChild(TA.utils.pill(this.esc(snap.market), "pill-muted"));
    left.appendChild(sub);
    head.appendChild(left);

    const closeBtn = TA.utils.el("button", "drawer-close", "\u00d7");
    closeBtn.setAttribute("type", "button");
    closeBtn.setAttribute("aria-label", "Close detail");
    closeBtn.addEventListener("click", () => this.close());
    head.appendChild(closeBtn);
    return head;
  },

  _hero(snap) {
    const quote = snap.quote || {};
    const trend = snap.trend || {};
    const hero = TA.utils.el("div", "drawer-hero");
    const price = TA.utils.el("div", "hero-price", this.esc(TA.utils.fmtMoney(quote.price, quote.currency)));
    hero.appendChild(price);

    const row = TA.utils.el("div", "hero-row");
    const changes = TA.utils.el("div", "hero-changes");
    changes.appendChild(this._changeChip("1H", quote.change_1h_pct));
    changes.appendChild(this._changeChip("1D", quote.change_1d_pct));
    row.appendChild(changes);

    const meta = TA.utils.el("div", "hero-meta");
    if (trend.regime) meta.appendChild(TA.utils.pill(this.esc(trend.regime), this._regimeCls(trend.regime)));
    meta.appendChild(TA.utils.el("span", "muted-small", this.esc("Updated " + TA.utils.fmtTime(snap.ts))));
    row.appendChild(meta);

    hero.appendChild(row);
    return hero;
  },

  _changeChip(label, val) {
    const chip = TA.utils.el("span", "hero-change");
    chip.appendChild(TA.utils.el("span", "hero-change-label", this.esc(label)));
    const cls = "hero-change-val" + (val > 0 ? " pos" : val < 0 ? " neg" : "");
    chip.appendChild(TA.utils.el("span", cls, this.esc(TA.utils.fmtPctNum(val, 2))));
    return chip;
  },

  _scoreBullet(label, value) {
    const cell = TA.utils.el("div", "score-cell");
    cell.appendChild(TA.utils.el("div", "metric-label", this.esc(label)));
    const valRow = TA.utils.el("div", "score-cell-val");
    const num = this.esc(TA.utils.fmt(value, 0));
    valRow.appendChild(TA.utils.scoreBar(value || 0));
    valRow.appendChild(TA.utils.el("span", "metric-num", num));
    cell.appendChild(valRow);
    return cell;
  },

  _fundSection(fund) {
    const wrap = TA.utils.el("div");
    const noData = fund.score === 0 && String(fund.note || "").trim().toLowerCase() === "no data";
    if (noData) {
      wrap.appendChild(TA.utils.pill("No fundamentals", "pill-muted"));
    } else {
      const grid = TA.utils.el("div", "score-grid");
      grid.appendChild(this._scoreBullet("Health", fund.health));
      grid.appendChild(this._scoreBullet("Valuation", fund.valuation));
      grid.appendChild(this._scoreBullet("Overall", fund.score));
      wrap.appendChild(grid);
    }
    if (fund.note) wrap.appendChild(TA.utils.el("div", "muted-small", this.esc(fund.note)));
    return wrap;
  },

  _regimeCls(r) {
    const s = String(r || "").toLowerCase();
    if (s === "bull") return "pill-bull";
    if (s === "bear") return "pill-bear";
    return "pill-mixed";
  },

  _trendSection(trend) {
    const wrap = TA.utils.el("div");
    const grid = TA.utils.el("div", "d-grid");
    if (trend.regime) grid.appendChild(this._metric("Regime", TA.utils.pill(this.esc(trend.regime), this._regimeCls(trend.regime))));
    grid.appendChild(this._metric("Trend Score", TA.utils.scoreBar(trend.trend_score || 0)));
    if (trend.strength !== undefined && trend.strength !== null) grid.appendChild(this._metric("Strength", TA.utils.confBar(trend.strength)));
    if (trend.ema_stack) grid.appendChild(this._metric("EMA Stack", TA.utils.el("span", null, this.esc(trend.ema_stack))));
    if (trend.adx !== undefined && trend.adx !== null) grid.appendChild(this._metric("ADX", TA.utils.el("span", null, this.esc(TA.utils.fmt(trend.adx, 1)))));
    wrap.appendChild(grid);

    const mc = trend.market_context;
    if (mc) {
      const box = TA.utils.el("div", "market-context");
      box.appendChild(TA.utils.el("div", "d-label", this.esc("Market Context")));
      const bg = TA.utils.el("div", "d-grid");
      if (mc.regime) bg.appendChild(this._metric("Regime", TA.utils.pill(this.esc(mc.regime), this._regimeCls(mc.regime))));
      if (mc.breadth !== undefined && mc.breadth !== null) bg.appendChild(this._metric("Breadth", TA.utils.el("span", null, this.esc(TA.utils.fmtPctRatio(mc.breadth, 1)))));
      if (mc.mean_momentum !== undefined && mc.mean_momentum !== null) bg.appendChild(this._metric("Momentum", TA.utils.el("span", null, this.esc(TA.utils.fmtPctRatio(mc.mean_momentum, 1)))));
      if (mc.n_up !== undefined || mc.n_total !== undefined) bg.appendChild(this._metric("Count", TA.utils.el("span", null, this.esc((mc.n_up || 0) + "/" + (mc.n_total || 0)))));
      box.appendChild(bg);
      if (mc.context_note) box.appendChild(TA.utils.el("div", "muted-small", this.esc(mc.context_note)));
      wrap.appendChild(box);
    }
    return wrap;
  },

  _signalsSection(signals) {
    if (!signals || !signals.length) return null;
    const sec = TA.utils.el("div", "drawer-section");
    sec.appendChild(TA.utils.el("div", "d-label", this.esc("Signals — " + this.HORIZON_ORDER.length + " horizons")));
    const list = TA.utils.el("div", "signals");
    let any = false;
    this.HORIZON_ORDER.forEach((h) => {
      const sig = signals.find((s) => s && s.horizon === h);
      if (!sig) return;
      any = true;
      list.appendChild(this._signalTile(sig));
    });
    if (!any) return null;
    sec.appendChild(list);
    return sec;
  },

  _signalTile(sig) {
    const tile = TA.utils.el("div", "signal-tile");
    const head = TA.utils.el("div", "signal-head");
    head.appendChild(TA.utils.badgeMeasure(this.esc(sig.action || "—"), TA.utils.actionFor(sig.score || 0)));
    head.appendChild(TA.utils.el("span", "signal-horizon", this.esc(sig.horizon)));
    tile.appendChild(head);

    const gaugeWrap = TA.utils.el("div", "gauge-wrap");
    if (sig.probability_up !== undefined && sig.probability_up !== null &&
        TA.charts && typeof TA.charts.gauge === "function") {
      const res = TA.charts.gauge(gaugeWrap, sig.probability_up);
      if (res && typeof res.nodeType === "number" && !gaugeWrap.contains(res)) gaugeWrap.appendChild(res);
    }
    tile.appendChild(gaugeWrap);

    if (sig.confidence !== undefined && sig.confidence !== null) {
      tile.appendChild(this._metric("Confidence", TA.utils.confBar(sig.confidence)));
    }

    if (sig.ml_probability !== undefined && sig.ml_probability !== null) {
      const chip = TA.utils.pill(this.esc("ML " + TA.utils.fmtPctRatio(sig.ml_probability, 0)), "pill-muted");
      tile.appendChild(chip);
    }

    const drivers = sig.drivers || {};
    const keys = Object.keys(drivers).slice(0, 3);
    if (keys.length) {
      const grid = TA.utils.el("div", "driver-grid");
      keys.forEach((k) => {
        const v = drivers[k];
        const cell = TA.utils.el("div", "driver-cell");
        cell.appendChild(TA.utils.el("span", "driver-key", this.esc(this._human(k))));
        const cls = "driver-val" + (v > 0 ? " pos" : v < 0 ? " neg" : "");
        cell.appendChild(TA.utils.el("span", cls, this.esc(TA.utils.fmtPctNum(v, 2))));
        grid.appendChild(cell);
      });
      tile.appendChild(grid);
    }
    return tile;
  },

  _human(key) {
    return String(key || "")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
  },

  _techSection(technical, trend) {
    if (!technical || typeof technical !== "object") return null;
    const keys = Object.keys(technical).filter((k) => k !== "daily");
    if (!keys.length) return null;

    let tf = (trend && trend.primary_timeframe) || "1d";
    if (tf === "daily" || !technical[tf]) tf = keys.includes("1d") ? "1d" : keys[0];

    const t = technical[tf] || technical[keys[0]];
    if (!t || typeof t !== "object") return null;

    const sec = TA.utils.el("div", "drawer-section");
    sec.appendChild(TA.utils.el("div", "d-label", this.esc("Technical · " + String(tf).toUpperCase())));
    const r = t.readings || {};
    const grid = TA.utils.el("div", "d-grid");
    const numRow = (label, val, d) => {
      if (val === undefined || val === null) return;
      grid.appendChild(this._metric(label, TA.utils.el("span", null, this.esc(TA.utils.fmt(val, d)))));
    };
    numRow("RSI", r.rsi, 1);
    numRow("Stoch %K", r.stoch_k, 1);
    numRow("Stoch %D", r.stoch_d, 1);
    numRow("ATR%", r.atr_pct, 2);
    numRow("ADX", r.adx, 1);
    numRow("CMF", r.cmf, 2);
    numRow("VWAP z", r.vwap_z, 2);
    numRow("Vol ratio", r.vol_ratio, 2);
    numRow("BB pos", r.bb_position, 2);
    if (r.last_pattern) grid.appendChild(this._metric("Pattern", TA.utils.el("span", null, this.esc(r.last_pattern))));
    sec.appendChild(grid);

    const s = t.subscores || {};
    const defs = [["momentum", "Momentum"], ["oscillator", "Oscillator"], ["trend", "Trend"], ["volume", "Volume"], ["volatility", "Volatility"], ["candle", "Candle"]];
    const sub = TA.utils.el("div", "d-grid sub-grid");
    defs.forEach(([k, label]) => {
      const v = s[k];
      if (v === undefined || v === null) return;
      sub.appendChild(this._metric(label, TA.utils.scoreBar(v)));
    });
    if (sub.children.length) sec.appendChild(sub);
    return sec;
  },

  _quoteStats(quote) {
    const grid = TA.utils.el("div", "d-grid");
    grid.appendChild(this._metric("Volume 24h", TA.utils.el("span", null, this.esc(TA.utils.fmtCompact(quote.volume_24h)))));
    grid.appendChild(this._metric("Market Cap", TA.utils.el("span", null, this.esc(TA.utils.fmtCompact(quote.market_cap)))));
    return grid;
  },

  esc(s) {
    return TA.utils.esc(s);
  },

  close() {
    const drawer = document.getElementById("detail-drawer");
    const backdrop = document.getElementById("detail-backdrop");
    if (drawer) {
      drawer.classList.remove("open");
      drawer.classList.add("hidden");
    }
    if (backdrop) backdrop.classList.add("hidden");
    TA.state.selected = null;
  }
};
