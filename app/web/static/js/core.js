window.TA = window.TA || {};

TA.state = {
  snapshots: new Map(),
  alerts: [],
  marketCtx: null,
  crowd: null,
  sortKey: "composite_score",
  sortDir: -1,
  selected: null,
  connected: false,
  initialLoaded: false,
  theme: "dark",
  tableQuery: ""
};

TA.core = {
  _sse: null,
  _pollTimer: null,
  _polling: false,
  _clockTimer: null,
  _errTimer: null,

  init() {
    try {
      const savedTheme = localStorage.getItem("ta-theme") || "dark";
      this.setTheme(savedTheme);

      const themeToggle = document.getElementById("theme-toggle");
      if (themeToggle) themeToggle.addEventListener("click", () => {
        try { this.setTheme(TA.state.theme === "dark" ? "light" : "dark"); } catch (e) { console.warn(e); }
      });

      const filter = document.getElementById("table-filter");
      if (filter) filter.addEventListener("input", (ev) => {
        try {
          TA.state.tableQuery = (ev.target.value || "").toLowerCase();
          TA.table?.renderTable && TA.table.renderTable();
        } catch (e) { console.warn(e); }
      });

      const alertsToggle = document.getElementById("alerts-toggle");
      if (alertsToggle) alertsToggle.addEventListener("click", () => {
        try { TA.alerts?.toggle && TA.alerts.toggle(); } catch (e) { console.warn(e); }
      });

      const alertsClear = document.getElementById("alerts-clear");
      if (alertsClear) alertsClear.addEventListener("click", () => {
        try { TA.alerts?.clear && TA.alerts.clear(); } catch (e) { console.warn(e); }
      });

      const thead = document.getElementById("table-head");
      if (thead) thead.addEventListener("click", (ev) => {
        try {
          const th = ev.target.closest("th[data-key]");
          if (th) TA.table?.sortBy && TA.table.sortBy(th.dataset.key);
        } catch (e) { console.warn(e); }
      });

      const tbody = document.getElementById("table-body");
      if (tbody) {
        tbody.addEventListener("click", (ev) => {
          try {
            const tr = ev.target.closest("tr[data-symbol]");
            if (!tr) return;
            this.openDetail(tr.dataset.symbol);
          } catch (e) { console.warn(e); }
        });
        tbody.addEventListener("keydown", (ev) => {
          try {
            if (ev.key !== "Enter") return;
            const tr = ev.target.closest("tr[data-symbol]");
            if (tr) this.openDetail(tr.dataset.symbol);
          } catch (e) { console.warn(e); }
        });
      }

      const watchList = document.getElementById("watch-list");
      if (watchList) {
        watchList.addEventListener("click", (ev) => {
          try {
            const card = ev.target.closest(".watch-card[data-symbol]");
            if (!card) return;
            this.openDetail(card.dataset.symbol);
          } catch (e) { console.warn(e); }
        });
      }

      window.addEventListener("resize", () => {
        try { this.renderAll(); } catch (e) { console.warn(e); }
      });

      const clock = document.getElementById("clock-display");
      const tickClock = () => {
        try {
          if (!clock) return;
          const d = new Date();
          const p = (x) => String(x).padStart(2, "0");
          clock.textContent = p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds());
        } catch (e) { console.warn(e); }
      };
      tickClock();
      this._clockTimer = setInterval(tickClock, 1000);

      if (window.EventSource) {
        this.connectSSE();
      } else {
        this.connectPoll();
      }
      this.fetchInitial();
    } catch (e) { console.warn(e); }
  },

  _mergeSnapshots(data) {
    try {
      if (data.snapshots && Array.isArray(data.snapshots)) {
        data.snapshots.forEach((s) => { if (s && s.symbol) TA.state.snapshots.set(s.symbol, s); });
      }
      if (data.market_context) TA.state.marketCtx = data.market_context;
    } catch (e) { console.warn(e); }
  },

  async fetchInitial() {
    try {
      const [snapRes, alertRes] = await Promise.all([
        fetch("/api/snapshots"),
        fetch("/api/alerts?limit=50")
      ]);
      const snapData = await snapRes.json();
      const alertData = await alertRes.json();
      this._mergeSnapshots(snapData);
      if (alertData && Array.isArray(alertData)) TA.state.alerts = alertData.slice();
      TA.alerts?.render && TA.alerts.render(TA.state.alerts);
      TA.state.initialLoaded = true;
      const loader = document.getElementById("loader");
      if (loader) loader.classList.add("hidden");
      this.renderAll();
      this.loadCrowd();
    } catch (e) {
      console.warn(e);
      const loader = document.getElementById("loader");
      if (loader) loader.classList.add("hidden");
      this.setError("Failed to load initial data");
    }
  },

  async loadCrowd() {
    try {
      const res = await fetch("/api/crowd");
      const data = await res.json();
      TA.state.crowd = data;
      TA.crowd?.render && TA.crowd.render(data);
      this.sayMarketCtx(TA.state.marketCtx);
    } catch (e) { console.warn(e); }
  },

  connectSSE() {
    try {
      if (this._sse) { try { this._sse.close(); } catch (e) {} this._sse = null; }
      let es;
      try {
        es = new EventSource("/api/stream");
      } catch (e) {
        console.warn(e);
        this.connectPoll();
        return;
      }
      this._sse = es;

      es.addEventListener("snapshot", (ev) => {
        try {
          const data = JSON.parse(ev.data);
          this._mergeSnapshots(data);
          this.renderAll();
        } catch (e) { console.warn(e); }
      });

      es.addEventListener("alert", (ev) => {
        try {
          const data = JSON.parse(ev.data);
          const list = (data.alerts && Array.isArray(data.alerts)) ? data.alerts : (data.alert ? [data.alert] : []);
          list.forEach((a) => {
            const key = (a.ts || "") + "|" + (a.symbol || "") + "|" + (a.kind || "");
            const dup = TA.state.alerts.some((x) => (x.ts || "") + "|" + (x.symbol || "") + "|" + (x.kind || "") === key);
            if (!dup) {
              TA.state.alerts.unshift(a);
              TA.alerts?.add && TA.alerts.add(a);
            }
          });
          this.sayMarketCtx(TA.state.marketCtx);
        } catch (e) { console.warn(e); }
      });

      es.addEventListener("ping", () => {
        try {
          TA.state.connected = true;
          this.setStatus("online", "live");
          this.updateMeta();
        } catch (e) { console.warn(e); }
      });

      es.addEventListener("crowd", (ev) => {
        try {
          const data = JSON.parse(ev.data);
          if (data && data.crowd) {
            TA.state.crowd = data.crowd;
            TA.crowd?.render && TA.crowd.render(data.crowd);
            this.sayMarketCtx(TA.state.marketCtx);
          }
        } catch (e) { console.warn(e); }
      });

      es.onerror = () => {
        try {
          TA.state.connected = false;
          this.setStatus("offline", "reconnecting…");
          if (this._sse) { try { this._sse.close(); } catch (e) {} this._sse = null; }
          setTimeout(() => { try { this.connectPoll(); } catch (e) { console.warn(e); } }, 5000);
        } catch (e) { console.warn(e); }
      };
    } catch (e) { console.warn(e); }
  },

  connectPoll() {
    try {
      if (this._polling) return;
      this._polling = true;
      const tick = async () => {
        try {
          const [snapRes, alertRes] = await Promise.all([
            fetch("/api/snapshots"),
            fetch("/api/alerts?limit=50")
          ]);
          const snapData = await snapRes.json();
          const alertData = await alertRes.json();
          this._mergeSnapshots(snapData);
          if (alertData && Array.isArray(alertData)) TA.state.alerts = alertData.slice();
          TA.state.connected = false;
          this.setStatus("polling", "polling");
          this.renderAll();
        } catch (e) {
          console.warn(e);
          this.setError("Poll failed");
        }
        this._pollTimer = setTimeout(tick, 15000);
      };
      this.setStatus("polling", "polling");
      tick();
    } catch (e) { console.warn(e); }
  },

  updateMeta() {
    try {
      const uts = document.getElementById("update-ts");
      if (uts) uts.textContent = TA.utils.fmtTime(new Date().toISOString());
    } catch (e) { console.warn(e); }
  },

  setStatus(cls, text) {
    try {
      const badge = document.getElementById("status-badge");
      if (!badge) return;
      badge.className = "badge badge-" + cls;
      if (text !== undefined && text !== null) {
        badge.textContent = "";
        const dot = document.createElement("span");
        dot.className = "dot-pulse";
        badge.appendChild(dot);
        badge.appendChild(document.createTextNode(" " + text));
      } else {
        badge.textContent = "";
      }
    } catch (e) { console.warn(e); }
  },

  sayMarketCtx(ctx) {
    try {
      const dash = "—";
      const regime = (ctx && ctx.regime) ? String(ctx.regime).toLowerCase() : "";
      const regimePill = regime === "bull" ? "pill-bull" : regime === "bear" ? "pill-bear" : (regime === "mixed" || regime === "sideways") ? "pill-mixed" : "pill-muted";

      const regimeEl = document.getElementById("ms-regime");
      if (regimeEl) {
        regimeEl.textContent = regime ? regime.toUpperCase() : dash;
        regimeEl.className = "ms-value pill " + regimePill;
      }

      const breadthEl = document.getElementById("ms-breadth");
      if (breadthEl) breadthEl.textContent = (ctx && ctx.breadth !== undefined && ctx.breadth !== null) ? TA.utils.fmtPctRatio(ctx.breadth, 0) : dash;

      const momentumEl = document.getElementById("ms-momentum");
      if (momentumEl) momentumEl.textContent = (ctx && ctx.mean_momentum !== undefined && ctx.mean_momentum !== null) ? TA.utils.fmtPctRatio(ctx.mean_momentum, 0) : dash;

      const countEl = document.getElementById("ms-count");
      if (countEl) countEl.textContent = String(TA.state.snapshots.size);

      const alertCountEl = document.getElementById("ms-alerts");
      if (alertCountEl) alertCountEl.textContent = String(TA.state.alerts.length);

      const crowdData = TA.state.crowd;
      const crowdEl = document.getElementById("ms-crowd");
      if (crowdEl) {
        const m = crowdData && crowdData.market ? crowdData.market : null;
        if (m && m.total_votes) {
          crowdEl.textContent = m.mood + " · " + m.total_votes + "v";
          crowdEl.className = "ms-value mono " +
            (m.mood === "BULLISH" ? "pos" : m.mood === "BEARISH" ? "neg" : "");
        } else {
          const st = crowdData && crowdData.status;
          crowdEl.textContent = st === "loading" ? "…" : dash;
          crowdEl.className = "ms-value mono muted-small";
        }
      }

      let up = 0, down = 0;
      TA.state.snapshots.forEach((s) => {
        const action = String((s.composite && s.composite.action) || "").toUpperCase();
        const words = action.split(/\s+/).slice(0, 2).join(" ");
        if (words.indexOf("BUY") !== -1) up++;
        else if (words.indexOf("SELL") !== -1) down++;
      });

      const upEl = document.getElementById("ms-up");
      if (upEl) upEl.textContent = String(up);
      const downEl = document.getElementById("ms-down");
      if (downEl) downEl.textContent = String(down);

      const pill = document.getElementById("market-pill");
      if (pill) {
        const breadthTxt = (ctx && ctx.breadth !== undefined && ctx.breadth !== null) ? TA.utils.fmtPctRatio(ctx.breadth, 0) : dash;
        pill.textContent = (regime ? regime : "unknown") + " · breadth " + breadthTxt;
        pill.className = "pill " + regimePill;
      }
    } catch (e) { console.warn(e); }
  },

  renderAll() {
    try {
      this.updateMeta();
      this.sayMarketCtx(TA.state.marketCtx);
      TA.table?.renderTable && TA.table.renderTable();
      if (window.matchMedia && window.matchMedia("(max-width: 720px)").matches) {
        TA.table?.renderMobileList && TA.table.renderMobileList();
      }
      if (TA.state.selected && TA.state.snapshots.has(TA.state.selected)) {
        TA.detail?.renderDetail && TA.detail.renderDetail(TA.state.selected);
      }
      const note = document.getElementById("table-note");
      if (note) {
        const classes = [];
        TA.state.snapshots.forEach((s) => {
          if (s.asset_class && classes.indexOf(s.asset_class) === -1) classes.push(s.asset_class);
        });
        note.textContent = TA.state.snapshots.size + " instruments tracked · " + (classes.join(", ") || "—") + " · live feed";
      }
    } catch (e) { console.warn(e); }
  },

  openDetail(symbol) {
    try {
      TA.state.selected = symbol;
      if (TA.detail) {
        const backdrop = document.getElementById("detail-backdrop");
        if (backdrop) backdrop.classList.remove("hidden");
        const drawer = document.getElementById("detail-drawer");
        if (drawer) {
          drawer.classList.remove("hidden");
          drawer.classList.add("open");
        }
        TA.detail.renderDetail && TA.detail.renderDetail(symbol);
      }
      TA.table?.renderTable && TA.table.renderTable();
    } catch (e) { console.warn(e); }
  },

  closeDetail() {
    try {
      TA.state.selected = null;
      const drawer = document.getElementById("detail-drawer");
      if (drawer) {
        drawer.classList.remove("open");
        drawer.classList.add("hidden");
      }
      const backdrop = document.getElementById("detail-backdrop");
      if (backdrop) backdrop.classList.add("hidden");
      if (TA.detail && typeof TA.detail.close === "function") TA.detail.close();
    } catch (e) { console.warn(e); }
  },

  setError(msg) {
    try {
      const banner = document.getElementById("error-banner");
      if (!banner) return;
      clearTimeout(this._errTimer);
      banner.textContent = msg;
      banner.classList.remove("hidden");
      this._errTimer = setTimeout(() => banner.classList.add("hidden"), 6000);
    } catch (e) { console.warn(e); }
  },

  setTheme(next) {
    try {
      TA.state.theme = (next === "light") ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", TA.state.theme);
      try { localStorage.setItem("ta-theme", TA.state.theme); } catch (e) {}
      const glyph = document.querySelector(".theme-glyph");
      if (glyph) glyph.classList.toggle("light", TA.state.theme === "light");
    } catch (e) { console.warn(e); }
  }
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => { try { TA.core.init(); } catch (e) { console.warn(e); } });
} else {
  try { TA.core.init(); } catch (e) { console.warn(e); }
}
