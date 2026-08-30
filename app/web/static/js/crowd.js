window.TA = window.TA || {};
TA.crowd = TA.crowd || {};

TA.crowd.render = function (data) {
  try {
    const U = TA.utils;
    const moodEl = document.getElementById("crowd-mood");
    const listEl = document.getElementById("crowd-list");
    const noteEl = document.getElementById("crowd-note");
    if (!moodEl || !listEl) return;

    const status = data && data.status;
    const market = data && data.market ? data.market : null;

    const liveBadge = document.getElementById("crowd-live");
    if (liveBadge) {
      const live = status === "ok" && market && market.total_votes;
      liveBadge.textContent = live ? "live" : "starting…";
      liveBadge.className = "pill " + (live ? "pill-bull" : "pill-muted");
    }

    if (!status || (status !== "ok" && status !== "loading")) {
      if (noteEl) noteEl.textContent = "Crowd engine not available.";
      moodEl.innerHTML = "";
      listEl.innerHTML = "";
      return;
    }

    if (status === "loading" || (market && !market.total_votes)) {
      if (noteEl) noteEl.textContent = "Fetching crowd predictions… (Fear & Greed + news sentiment)";
      moodEl.innerHTML = "";
      listEl.innerHTML = "";
      return;
    }

    const updated = data.updated_ts;
    if (noteEl) noteEl.textContent = "Live · Fear & Greed + news sentiment" + (updated ? " · " + U.fmtTime(updated) : "");

    moodEl.innerHTML = "";
    if (market) {
      const mood = market.mood || "EMPTY";
      const scorePct = Math.round((market.net_score || 0) * 100);
      const moodCls = mood === "BULLISH" ? "pill-bull" : mood === "BEARISH" ? "pill-bear" : (mood === "NEUTRAL" ? "pill-mixed" : "pill-muted");
      const row = U.el("div", "crowd-mood-row");
      const left = U.el("div", "crowd-mood-left");
      const label = U.el("div", "ms-label", "Market crowd mood");
      const badge = U.pill(mood + " " + (scorePct > 0 ? "+" : "") + scorePct + "%", moodCls);
      left.appendChild(label);
      left.appendChild(badge);
      const stats = U.el("div", "crowd-mood-stats");
      stats.appendChild(this._stat("Crowd signals", U.fmtCompact(market.total_votes || 0)));
      stats.appendChild(this._stat("Bullish", U.fmtCompact(market.bullish_votes || 0) + " · " + this._pct(market.bullish_votes, market.total_votes)));
      stats.appendChild(this._stat("Bearish", U.fmtCompact(market.bearish_votes || 0) + " · " + this._pct(market.bearish_votes, market.total_votes)));
      stats.appendChild(this._stat("Fear & Greed", market.fear_greed !== undefined && market.fear_greed !== null ? market.fear_greed + " · " + (market.fear_greed_label || "") : "—"));
      stats.appendChild(this._stat("Top pick", U.esc(market.top_symbol || "—")));
      stats.appendChild(this._stat("Coins", String(market.coins_with_data || 0)));
      row.appendChild(left);
      row.appendChild(stats);
      moodEl.appendChild(row);
    }

    const symbols = data.symbols || {};
    listEl.innerHTML = "";
    const entries = Object.keys(symbols)
      .map((k) => symbols[k])
      .filter((a) => a && a.total_votes);
    if (entries.length === 0) {
      listEl.appendChild(U.el("div", "alerts-empty muted-small", "No crowd sentiment yet — fetching news + Fear & Greed signals…"));
      return;
    }
    entries.sort((a, b) => (b.total_votes - a.total_votes));
    entries.forEach((a) => listEl.appendChild(this._tickerRow(a)));
  } catch (e) { console.warn(e); }
};

TA.crowd._tickerRow = function (a) {
  const U = TA.utils;
  const total = a.total_votes || 1;
  const bullShare = Math.round(((a.bullish_votes || 0) / total) * 100);
  const bearShare = Math.round(((a.bearish_votes || 0) / total) * 100);
  const scorePct = Math.round((a.score || 0) * 100);
  const bias = a.bias || "EMPTY";
  const biasCls = bias === "BULLISH" ? "pill-bull" : bias === "BEARISH" ? "pill-bear" : (bias === "NEUTRAL" ? "pill-mixed" : "pill-muted");

  const row = U.el("div", "crowd-row");
  const head = U.el("div", "crowd-row-head");
  const sym = U.el("span", "crowd-sym mono", U.esc(a.symbol));
  const meta = U.el("span", "crowd-meta muted-small", a.posts + " posts · " + U.fmtCompact(a.total_votes) + " votes");
  head.appendChild(sym);
  head.appendChild(meta);
  row.appendChild(head);

  const scale = U.el("div", "crowd-scale");
  const bull = U.el("div", "crowd-scale-bull");
  bull.style.width = bullShare + "%";
  const bear = U.el("div", "crowd-scale-bear");
  bear.style.width = bearShare + "%";
  scale.appendChild(bull);
  scale.appendChild(bear);
  row.appendChild(scale);

  const foot = U.el("div", "crowd-row-foot");
  const up = U.el("span", "pos mono", "▲ " + U.fmtCompact(a.bullish_votes || 0) + " (" + bullShare + "%)");
  const dn = U.el("span", "neg mono", "▼ " + U.fmtCompact(a.bearish_votes || 0) + " (" + bearShare + "%)");
  const badge = U.pill(bias + (scorePct !== 0 ? " " + (scorePct > 0 ? "+" : "") + scorePct + "%" : ""), biasCls);
  foot.appendChild(up);
  foot.appendChild(dn);
  foot.appendChild(badge);
  row.appendChild(foot);
  return row;
};

TA.crowd._stat = function (label, value) {
  const U = TA.utils;
  const cell = U.el("div", "crowd-stat");
  const lab = U.el("span", "metric-label", U.esc(label));
  const val = U.el("span", "crowd-stat-val mono", String(value));
  cell.appendChild(lab);
  cell.appendChild(val);
  return cell;
};

TA.crowd._pct = function (part, total) {
  if (!total) return "0%";
  return Math.round((part / total) * 100) + "%";
};
