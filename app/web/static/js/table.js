window.TA = window.TA || {};

(function () {
  const HORDER = ["1MIN", "5MIN", "1H", "6H", "1D"];

  const COLUMNS = [
    { k: "symbol", label: "Symbol" },
    { k: "name", label: "Asset" },
    { k: "price", label: "Price", right: true },
    { k: "change_1h_pct", label: "1H", right: true },
    { k: "change_1d_pct", label: "1D", right: true },
    { k: "trend", label: "Trend" },
    { k: "signals", label: "Signals", sortable: false },
    { k: "fund", label: "Fund", right: true },
    { k: "composite_score", label: "Composite", right: true }
  ];

  function sortValue(snap, key) {
    if (!snap) return null;
    const q = snap.quote || {};
    if (key === "symbol") return String(snap.symbol || "").toLowerCase();
    if (key === "name") return String(snap.name || "").toLowerCase();
    if (key === "price") return q.price;
    if (key === "change_1h_pct") return q.change_1h_pct;
    if (key === "change_1d_pct") return q.change_1d_pct;
    if (key === "trend") {
      const rank = { BULL: 2, MIXED: 1, BEAR: 0 };
      return rank[snap.trend && snap.trend.regime] !== undefined ? rank[snap.trend.regime] : -1;
    }
    if (key === "fund") return (snap.fundamental && snap.fundamental.score) || null;
    if (key === "composite_score") return (snap.composite && snap.composite.score) || null;
    return null;
  }

  function buildHead() {
    const head = document.getElementById("table-head");
    if (!head) return;
    while (head.firstChild) head.removeChild(head.firstChild);
    const st = TA.state || {};
    const key = st.sortKey;
    const dir = st.sortDir === undefined || st.sortDir === null ? 1 : st.sortDir;
    for (let i = 0; i < COLUMNS.length; i++) {
      const col = COLUMNS[i];
      const sortable = col.sortable !== false;
      let cls = sortable ? "sortable" : "";
      if (col.right) cls = (cls ? cls + " " : "") + "num-cell";
      if (sortable && key === col.k) cls += dir > 0 ? " asc" : " desc";
      const th = TA.utils.el("th", cls, TA.utils.esc(col.label));
      th.setAttribute("data-key", col.k);
      if (!sortable) th.setAttribute("data-sortable", "false");
      head.appendChild(th);
    }
  }

  function sortBy(key) {
    if (!key || key === "signals") return;
    const st = (TA.state = TA.state || {});
    if (st.sortKey === key) {
      st.sortDir = (st.sortDir || 1) * -1;
    } else {
      st.sortKey = key;
      st.sortDir = 1;
    }
    buildHead();
    renderTable();
  }

  function filterList(list) {
    const q = (TA.state && TA.state.tableQuery || "").toLowerCase().trim();
    if (!q) return list;
    const out = [];
    for (let i = 0; i < list.length; i++) {
      const s = list[i];
      const sym = String(s.symbol || "").toLowerCase();
      const name = String(s.name || "").toLowerCase();
      const ac = String(s.asset_class || "").toLowerCase();
      const mkt = String(s.market || "").toLowerCase();
      if (sym.indexOf(q) !== -1 || name.indexOf(q) !== -1 || ac.indexOf(q) !== -1 || mkt.indexOf(q) !== -1) {
        out.push(s);
      }
    }
    return out;
  }

  function sortList(list) {
    const st = TA.state || {};
    const key = st.sortKey;
    if (!key) return list.slice();
    const dir = st.sortDir === undefined || st.sortDir === null ? 1 : st.sortDir;
    const strKeys = ["symbol", "name"];
    return list.slice().sort(function (a, b) {
      const va = sortValue(a, key);
      const vb = sortValue(b, key);
      let cmp;
      if (strKeys.indexOf(key) !== -1) {
        const sa = va === null || va === undefined ? "" : String(va);
        const sb = vb === null || vb === undefined ? "" : String(vb);
        cmp = sa < sb ? -1 : sa > sb ? 1 : 0;
      } else {
        const na = va === null || va === undefined || isNaN(va) ? -Infinity : va;
        const nb = vb === null || vb === undefined || isNaN(vb) ? -Infinity : vb;
        cmp = na - nb;
      }
      return cmp * dir;
    });
  }

  function posNeg(v) {
    return v === null || v === undefined || isNaN(v) ? "" : v > 0 ? " pos" : v < 0 ? " neg" : "";
  }

  function row(snap) {
    const tr = TA.utils.el("tr");
    tr.setAttribute("data-symbol", snap.symbol || "");
    if (TA.state && TA.state.selected && TA.state.selected === snap.symbol) tr.classList.add("selected");

    const symbolCell = TA.utils.el("td");
    const sym = TA.utils.el("strong", "mono");
    sym.textContent = snap.symbol || "\u2014";
    symbolCell.appendChild(sym);
    if (snap.asset_class || snap.market || snap.provider) {
      const parts = [];
      if (snap.asset_class) parts.push(snap.asset_class);
      if (snap.market) parts.push(snap.market);
      if (snap.provider) parts.push(snap.provider);
      const sub = TA.utils.el("div", "muted-small mono");
      sub.textContent = parts.join(" \u00B7 ");
      symbolCell.appendChild(sub);
    }
    tr.appendChild(symbolCell);

    const nameCell = TA.utils.el("td");
    const name = TA.utils.el("div");
    name.textContent = snap.name || "\u2014";
    nameCell.appendChild(name);
    if (snap.name) {
      const sub = TA.utils.el("div", "muted-small");
      sub.textContent = snap.name;
      nameCell.appendChild(sub);
    }
    tr.appendChild(nameCell);

    const q = snap.quote || {};
    const currency = q.currency || "";

    const priceCell = TA.utils.el("td", "num-cell");
    const price = TA.utils.el("div", "mono");
    price.textContent = TA.utils.fmtMoney(q.price, currency);
    priceCell.appendChild(price);
    if (q.change_1d_pct !== null && q.change_1d_pct !== undefined) {
      const sub = TA.utils.el("div", "muted-small" + posNeg(q.change_1d_pct));
      sub.textContent = TA.utils.fmtPctNum(q.change_1d_pct);
      priceCell.appendChild(sub);
    }
    tr.appendChild(priceCell);

    const c1hCell = TA.utils.el("td", "num-cell mono" + posNeg(q.change_1h_pct));
    c1hCell.textContent = q.change_1h_pct === null || q.change_1h_pct === undefined
      ? "\u2014" : TA.utils.fmtPctNum(q.change_1h_pct);
    tr.appendChild(c1hCell);

    const c1dCell = TA.utils.el("td", "num-cell mono" + posNeg(q.change_1d_pct));
    c1dCell.textContent = q.change_1d_pct === null || q.change_1d_pct === undefined
      ? "\u2014" : TA.utils.fmtPctNum(q.change_1d_pct);
    tr.appendChild(c1dCell);

    const trend = snap.trend || {};
    const regime = trend.regime ? String(trend.regime).toUpperCase() : "\u2014";
    const cls = regime === "BULL" ? "pill-bull" : regime === "BEAR" ? "pill-bear" : regime === "MIXED" ? "pill-mixed" : "pill-muted";
    const trendCell = TA.utils.el("td");
    trendCell.appendChild(TA.utils.pill(regime, cls));
    if (trend.strength !== null && trend.strength !== undefined) {
      const str = TA.utils.el("div", "num muted-small");
      str.textContent = TA.utils.fmt(trend.strength, 0);
      trendCell.appendChild(str);
    }
    tr.appendChild(trendCell);

    const signalsCell = TA.utils.el("td");
    signalsCell.appendChild(TA.utils.signalStrip(snap.signals, HORDER));
    tr.appendChild(signalsCell);

    const fund = snap.fundamental || {};
    const fundCell = TA.utils.el("td", "num-cell");
    fundCell.appendChild(TA.utils.scoreBar(fund.score));
    if (fund.score !== null && fund.score !== undefined) {
      const num = TA.utils.el("div", "num muted-small");
      num.textContent = TA.utils.fmt(fund.score, 0);
      fundCell.appendChild(num);
    }
    tr.appendChild(fundCell);

    const composite = snap.composite || {};
    const compositeCell = TA.utils.el("td", "num-cell");
    const action = String(composite.action || "").split(/\s+/);
    const actionShort = action.length ? action[0].slice(0, 3) : "\u2014";
    const badge = TA.utils.badgeMeasure(actionShort, TA.utils.actionFor(composite.score));
    if (composite.bias !== null && composite.bias !== undefined) {
      badge.title = "bias " + composite.bias;
    }
    compositeCell.appendChild(badge);
    if (composite.score !== null && composite.score !== undefined) {
      const num = TA.utils.el("div", "num muted-small");
      num.textContent = TA.utils.fmt(composite.score, 0);
      compositeCell.appendChild(num);
    }
    tr.appendChild(compositeCell);

    return tr;
  }

  function mobileCard(snap) {
    const card = TA.utils.el("li", "watch-card");
    card.setAttribute("data-symbol", snap.symbol || "");
    if (TA.state && TA.state.selected && TA.state.selected === snap.symbol) card.classList.add("selected");

    const q = snap.quote || {};
    const currency = q.currency || "";

    const top = TA.utils.el("div", "watch-top");
    const left = TA.utils.el("div", "watch-id");
    const sym = TA.utils.el("div", "watch-symbol mono");
    sym.textContent = snap.symbol || "\u2014";
    left.appendChild(sym);
    const name = TA.utils.el("div", "watch-name muted-small");
    name.textContent = snap.name || "";
    left.appendChild(name);
    top.appendChild(left);

    const side = TA.utils.el("div", "watch-side");
    const mkt = TA.utils.el("div", "watch-mkt muted-small mono");
    mkt.textContent = (snap.asset_class || "") + (snap.market ? " \u00B7 " + snap.market : "");
    side.appendChild(mkt);

    const t = snap.trend || {};
    const trPill = TA.utils.pill(t.regime || "\u2014",
      t.regime === "BULL" ? "pill-bull" : t.regime === "BEAR" ? "pill-bear" : t.regime === "MIXED" ? "pill-mixed" : "pill-muted");
    side.appendChild(trPill);
    top.appendChild(side);

    card.appendChild(top);

    const priceRow = TA.utils.el("div", "watch-price-row");
    const price = TA.utils.el("span", "watch-price mono");
    price.textContent = TA.utils.fmtMoney(q.price, currency);
    priceRow.appendChild(price);
    if (q.change_1d_pct !== null && q.change_1d_pct !== undefined) {
      const chg = TA.utils.el("span", "watch-chg mono" + posNeg(q.change_1d_pct));
      chg.textContent = TA.utils.fmtPctNum(q.change_1d_pct);
      priceRow.appendChild(chg);
    }
    const comp = snap.composite || {};
    if (comp.score !== null && comp.score !== undefined) {
      const compBadge = TA.utils.badgeMeasure(String(comp.action || "\u2014").split(/\s+/)[0].slice(0, 3), TA.utils.actionFor(comp.score));
      compBadge.title = "Composite " + comp.score;
      const wrap = TA.utils.el("span", "watch-comp");
      wrap.appendChild(compBadge);
      priceRow.appendChild(wrap);
    }
    card.appendChild(priceRow);

    const sigRow = TA.utils.el("div", "watch-sig");
    sigRow.appendChild(TA.utils.signalStrip(snap.signals, HORDER));
    card.appendChild(sigRow);

    return card;
  }

  const CATEGORY = { crypto: "Crypto", equity: "Stocks" };
  const CATEGORY_ORDER = ["crypto", "equity"];

  function categoryLabel(snap) {
    return CATEGORY[snap && snap.asset_class] || "Other";
  }

  function categoryRow(label) {
    const tr = TA.utils.el("tr", "category-row");
    const td = TA.utils.el("td", "category-cell");
    td.setAttribute("colspan", String(COLUMNS.length + 1));
    const chip = TA.utils.el("span", "category-chip");
    chip.textContent = label;
    td.appendChild(chip);
    tr.appendChild(td);
    return tr;
  }

  function categoryHeader(label) {
    const li = TA.utils.el("li", "watch-category");
    const span = TA.utils.el("span", "watch-category-label");
    span.textContent = label;
    li.appendChild(span);
    return li;
  }

  function groupByCategory(sorted) {
    const groups = {};
    CATEGORY_ORDER.forEach(function (c) {
      groups[c] = [];
    });
    sorted.forEach(function (s) {
      const c = CATEGORY[s && s.asset_class] ? s.asset_class : "Other";
      if (!groups[c]) groups[c] = [];
      groups[c].push(s);
    });
    return groups;
  }

  function renderTable() {
    const container = document.getElementById("table-wrap");
    const body = document.getElementById("table-body");
    if (!container || !body) return;

    const isMobile = window.matchMedia("(max-width: 720px)").matches;
    container.classList.toggle("is-mobile", isMobile);

    if (isMobile) {
      renderMobileList();
      return;
    }

    if (!document.getElementById("table-head") || !document.getElementById("table-head").firstChild) buildHead();
    while (body.firstChild) body.removeChild(body.firstChild);
    const map = (TA.state && TA.state.snapshots) || new Map();
    const list = [];
    map.forEach(function (s) {
      if (s) list.push(s);
    });
    const filtered = filterList(list);
    const sorted = sortList(filtered);
    const groups = groupByCategory(sorted);
    CATEGORY_ORDER.forEach(function (c) {
      const items = groups[c];
      if (!items || !items.length) return;
      body.appendChild(categoryRow(categoryLabel(items[0])));
      items.forEach(function (s) {
        body.appendChild(row(s));
      });
    });
  }

  function renderMobileList() {
    const wrap = document.querySelector(".watch-list");
    if (!wrap) return;
    wrap.innerHTML = "";
    const map = (TA.state && TA.state.snapshots) || new Map();
    const list = [];
    map.forEach(function (s) {
      if (s) list.push(s);
    });
    const filtered = filterList(list);
    const sorted = sortList(filtered);
    const groups = groupByCategory(sorted);
    CATEGORY_ORDER.forEach(function (c) {
      const items = groups[c];
      if (!items || !items.length) return;
      wrap.appendChild(categoryHeader(categoryLabel(items[0])));
      items.forEach(function (s) {
        wrap.appendChild(mobileCard(s));
      });
    });
  }

  TA.table = {
    labels: {
      symbol: "Symbol",
      name: "Asset",
      price: "Price",
      change_1h_pct: "1H",
      change_1d_pct: "1D",
      trend: "Trend",
      signals: "Signals",
      fund: "Fund",
      composite_score: "Composite"
    },
    buildHead: buildHead,
    sortBy: sortBy,
    sortValue: sortValue,
    renderTable: renderTable,
    renderMobileList: renderMobileList,
    row: row,
    mobileCard: mobileCard
  };

  function initHead() {
    if (document.getElementById("table-head") && !document.getElementById("table-head").firstChild) {
      buildHead();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initHead);
  } else {
    initHead();
  }
})();
