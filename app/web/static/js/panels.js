window.TA = window.TA || {};
TA.panels = TA.panels || {};

TA.panels.renderConsensus = function (data) {
  try {
    const U = TA.utils;
    const el = document.getElementById("consensus");
    const note = document.getElementById("consensus-note");
    if (!el) return;

    const ok = data && data.status === "ok" && data.n_symbols;

    if (!ok) {
      if (note) note.textContent = "waiting for live data…";
      el.innerHTML = "";
      el.appendChild(U.el("div", "panel-wait", U.esc(data && data.status === "empty" ? "Waiting for the first analysis cycle — data will appear shortly…" : "Market consensus unavailable.")));
      return;
    }

    if (note) note.textContent = "Market-wide aggregation · " + U.fmtCompact(data.n_symbols) + " symbols · " + U.fmtCompact(data.n_signals) + " signals";

    const dir = data.consensus_direction === "BULLISH" ? "pill-bull" : data.consensus_direction === "BEARISH" ? "pill-bear" : "pill-mixed";
    const tiltCls = (data.net_tilt || 0) >= 0 ? "pos" : "neg";
    const tiltArrow = (data.net_tilt || 0) >= 0 ? "▲" : "▼";

    const hero = U.el("div", "consensus-hero");
    const heroTop = U.el("div", "consensus-hero-top");
    const badge = U.pill(data.consensus_direction + " · strength " + U.fmt((data.consensus_strength || 0) * 100, 1) + "%", dir);
    badge.classList.add("consensus-badge");
    heroTop.appendChild(badge);

    const share = U.el("div", "consensus-share");
    share.appendChild(this._shareBar(data));
    share.appendChild(this._shareLabels(data));
    hero.appendChild(heroTop);
    hero.appendChild(share);

    const metrics = U.el("div", "consensus-metrics");
    metrics.appendChild(this._metric("Avg composite", U.fmt(data.avg_composite, 1), (data.avg_composite || 0) >= 0 ? "pos" : "neg"));
    metrics.appendChild(this._metric("Avg prob up", U.fmt((data.avg_probability_up || 0) * 100, 1) + "%", ""));
    metrics.appendChild(this._metric("Net tilt", tiltArrow + " " + U.fmtPctNum((data.net_tilt || 0) * 100, 1), tiltCls));
    metrics.appendChild(this._metric("Avg risk", U.fmt(data.avg_risk_pct, 2) + "%", "neg"));
    metrics.appendChild(this._metric("Avg reward", U.fmt(data.avg_reward_pct, 2) + "%", "pos"));

    el.innerHTML = "";
    el.appendChild(hero);
    el.appendChild(metrics);

    const boards = U.el("div", "consensus-boards");
    boards.appendChild(this._leaderboard("Top Buys", data.top_buys, true));
    boards.appendChild(this._leaderboard("Top Sells", data.top_sells, false));
    el.appendChild(boards);
  } catch (e) { console.warn(e); }
};

TA.panels._shareBar = function (data) {
  const U = TA.utils;
  const bar = U.el("div", "ratio-bar");
  const b = U.el("div", "ratio-fill-pos");
  b.style.width = U.clamp(data.bullish_share || 0, 0, 100) + "%";
  const n = U.el("div", "ratio-fill-mix");
  n.style.width = U.clamp(data.neutral_share || 0, 0, 100) + "%";
  const s = U.el("div", "ratio-fill-neg");
  s.style.width = U.clamp(data.bearish_share || 0, 0, 100) + "%";
  bar.appendChild(b);
  bar.appendChild(n);
  bar.appendChild(s);
  return bar;
};

TA.panels._shareLabels = function (data) {
  const U = TA.utils;
  const row = U.el("div", "share-labels");
  row.appendChild(U.el("span", "pos", "Bullish " + U.fmt(data.bullish_share, 1) + "%"));
  row.appendChild(U.el("span", "share-neut", "Neutral " + U.fmt(data.neutral_share, 1) + "%"));
  row.appendChild(U.el("span", "neg", "Bearish " + U.fmt(data.bearish_share, 1) + "%"));
  return row;
};

TA.panels._metric = function (label, value, cls) {
  const U = TA.utils;
  const cell = U.el("div", "con-metric");
  const lab = U.el("span", "metric-label", U.esc(label));
  const val = U.el("span", "con-metric-val mono " + cls, String(value));
  cell.appendChild(lab);
  cell.appendChild(val);
  return cell;
};

TA.panels._leaderboard = function (title, items, isBuy) {
  const U = TA.utils;
  const box = U.el("div", "lb-box" + (isBuy ? " lb-buy" : " lb-sell"));

  const head = U.el("div", "lb-head");
  const t = U.el("span", "lb-title", U.esc(title));
  head.appendChild(t);
  const count = U.el("span", "lb-count mono muted-small", String((items || []).length));
  head.appendChild(count);
  box.appendChild(head);

  const list = U.el("div", "lb-list");
  if (!items || items.length === 0) {
    list.appendChild(U.el("div", "panel-wait", "No " + (isBuy ? "buy" : "sell") + " signals yet — waiting for data…"));
  } else {
    items.forEach((r) => list.appendChild(this._lbRow(r, isBuy)));
  }
  box.appendChild(list);
  return box;
};

TA.panels._lbRow = function (r, isBuy) {
  const U = TA.utils;
  const row = U.el("div", "lb-row");
  const sym = U.el("span", "lb-cell lb-sym mono", U.esc(r.symbol));
  const horizon = U.el("span", "lb-cell lb-horizon", U.esc(r.horizon || ""));
  const actionCls = r.action === "SELL" ? "neg" : (r.action === "BUY" ? "pos" : "");
  const action = U.el("span", "lb-cell lb-action " + actionCls, U.esc(r.action || ""));
  const score = U.el("span", "lb-cell lb-score mono " + ((r.score || 0) >= 0 ? "pos" : "neg"), U.fmt(r.score, 1));

  const pctCls = ((r.probability_up || 0) * 100) >= 50 ? "pos" : "neg";
  const pct = U.el("span", "lb-cell lb-pct mono " + pctCls, U.fmt((r.probability_up || 0) * 100, 1) + "%");

  const px = U.el("span", "lb-cell lb-px mono");
  px.appendChild(U.el("span", "px-label muted-small", "E"));
  px.appendChild(document.createTextNode(" " + U.fmtMoney(r.entry)));
  px.appendChild(document.createElement("br"));
  px.appendChild(U.el("span", "px-label muted-small", "TP"));
  px.appendChild(document.createTextNode(" " + U.fmtMoney(r.take_profit)));
  px.appendChild(document.createElement("br"));
  px.appendChild(U.el("span", "px-label muted-small", "SL"));
  px.appendChild(document.createTextNode(" " + U.fmtMoney(r.stop_loss)));

  row.appendChild(sym);
  row.appendChild(horizon);
  row.appendChild(action);
  row.appendChild(score);
  row.appendChild(pct);
  row.appendChild(px);
  return row;
};

TA.panels.renderAccuracy = function (data) {
  try {
    const U = TA.utils;
    const el = document.getElementById("accuracy");
    const note = document.getElementById("accuracy-note");
    if (!el) return;

    if (!data || typeof data.hit_rate !== "number") {
      if (note) note.textContent = "sahi / ghalat ratio";
      el.innerHTML = "";
      el.appendChild(U.el("div", "panel-wait", "Waiting for prediction outcomes — data will appear once signals resolve…"));
      return;
    }

    if (note) note.textContent = "sahi / ghalat ratio · " + U.fmt(data.resolved) + " resolved · " + U.fmt(data.pending) + " pending";

    const wrap = U.el("div", "acc-wrap");

    const hero = U.el("div", "acc-hero");
    const big = U.el("div", "hit-big", U.fmt(data.hit_rate, 1) + "%");
    hero.appendChild(big);

    const bar = U.el("div", "ratio-bar");
    const good = U.el("div", "ratio-fill-pos");
    good.style.width = U.clamp(data.hit_rate, 0, 100) + "%";
    const bad = U.el("div", "ratio-fill-neg");
    bad.style.width = U.clamp(100 - data.hit_rate, 0, 100) + "%";
    bar.appendChild(good);
    bar.appendChild(bad);
    hero.appendChild(bar);

    const counts = U.el("div", "acc-counts");
    counts.appendChild(this._count("Resolved", U.fmt(data.resolved || 0), ""));
    counts.appendChild(this._count("Correct", U.fmt(data.correct || 0), "pos"));
    counts.appendChild(this._count("Wrong", U.fmt(data.wrong || 0), "neg"));
    counts.appendChild(this._count("Pending", U.fmt(data.pending || 0), "muted-small"));
    hero.appendChild(counts);
    wrap.appendChild(hero);

    const horizons = data.by_horizon || {};
    const hKeys = Object.keys(horizons);
    if (hKeys.length) {
      const hSec = U.el("div", "acc-section");
      hSec.appendChild(U.el("div", "acc-sec-title", "By horizon"));
      hKeys.sort().forEach((k) => hSec.appendChild(this._horizonRow(k, horizons[k])));
      wrap.appendChild(hSec);
    }

    const symbols = data.by_symbol || [];
    if (symbols.length) {
      const sSec = U.el("div", "acc-section");
      sSec.appendChild(U.el("div", "acc-sec-title", "By symbol"));
      const list = U.el("div", "acc-symbols");
      symbols.forEach((s) => list.appendChild(this._symbolRow(s)));
      sSec.appendChild(list);
      wrap.appendChild(sSec);
    }

    el.innerHTML = "";
    el.appendChild(wrap);
  } catch (e) { console.warn(e); }
};

TA.panels._count = function (label, value, cls) {
  const U = TA.utils;
  const cell = U.el("div", "acc-count mono " + cls, String(value));
  cell.title = label;
  const lab = U.el("span", "acc-count-label", U.esc(label));
  const box = U.el("div", "acc-count-box");
  box.appendChild(cell);
  box.appendChild(lab);
  return box;
};

TA.panels._horizonRow = function (key, h) {
  const U = TA.utils;
  const row = U.el("div", "acc-row");
  const label = U.el("span", "acc-row-label mono", U.esc(key));
  row.appendChild(label);

  const pct = U.el("div", "pct-bar");
  const fill = U.el("div", "pct-fill " + ((h.hit_rate || 0) >= 50 ? "pct-pos" : "pct-neg"));
  fill.style.width = U.clamp(h.hit_rate || 0, 0, 100) + "%";
  pct.appendChild(fill);
  row.appendChild(pct);

  const meta = U.el("span", "acc-row-meta mono", U.fmt(h.correct) + "/" + U.fmt(h.n) + " · " + U.fmt(h.hit_rate, 1) + "%");
  row.appendChild(meta);
  return row;
};

TA.panels._symbolRow = function (s) {
  const U = TA.utils;
  const row = U.el("div", "acc-row");
  const label = U.el("span", "acc-row-label mono", U.esc(s.symbol));
  row.appendChild(label);

  const pct = U.el("div", "pct-bar");
  const fill = U.el("div", "pct-fill " + ((s.hit_rate || 0) >= 50 ? "pct-pos" : "pct-neg"));
  fill.style.width = U.clamp(s.hit_rate || 0, 0, 100) + "%";
  pct.appendChild(fill);
  row.appendChild(pct);

  const meta = U.el("span", "acc-row-meta mono", U.fmt(s.correct) + "/" + U.fmt(s.n) + " · " + U.fmt(s.hit_rate, 1) + "%");
  row.appendChild(meta);
  return row;
};
