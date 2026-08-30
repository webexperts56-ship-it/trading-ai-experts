window.TA = window.TA || {};

TA.utils = {
  el(tag, cls, html) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (html !== undefined && html !== null) node.innerHTML = html;
    return node;
  },

  esc(s) {
    if (s === null || s === undefined) return "";
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  },

  fmt(n, digits = 0) {
    if (n === null || n === undefined || isNaN(n)) return "-";
    return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  },

  fmtPctRatio(r, digits = 1) {
    if (r === null || r === undefined || isNaN(r)) return "-";
    return (r > 0 ? "+" : "") + (r * 100).toFixed(digits) + "%";
  },

  fmtPctNum(x, digits = 2) {
    if (x === null || x === undefined || isNaN(x)) return "-";
    return (x > 0 ? "+" : "") + x.toFixed(digits) + "%";
  },

  fmtMoney(n, cur, compact = false) {
    if (n === null || n === undefined || isNaN(n)) return "-";
    const c = cur === undefined || cur === null ? "" : cur;
    let out;
    const a = Math.abs(n);
    if (compact && a >= 1000) {
      out = this.fmtCompact(n);
    } else if (a < 100) {
      out = n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    } else {
      out = n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    }
    return out + c;
  },

  fmtCompact(n) {
    if (n === null || n === undefined || isNaN(n)) return "-";
    const a = Math.abs(n);
    const sign = n < 0 ? "-" : "";
    if (a >= 1e12) return sign + (a / 1e12).toFixed(1).replace(/\.0$/, "") + "T";
    if (a >= 1e9) return sign + (a / 1e9).toFixed(1).replace(/\.0$/, "") + "B";
    if (a >= 1e6) return sign + (a / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
    if (a >= 1000) return sign + (a / 1000).toFixed(1).replace(/\.0$/, "") + "K";
    return sign + a;
  },

  fmtTime(iso) {
    if (!iso) return "-";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "-";
    const p = (x) => String(x).padStart(2, "0");
    return p(d.getUTCHours()) + ":" + p(d.getUTCMinutes()) + ":" + p(d.getUTCSeconds()) + " UTC";
  },

  clamp(v, lo, hi) {
    if (v === null || v === undefined || isNaN(v)) return lo;
    return Math.max(lo, Math.min(hi, v));
  },

  actionFor(score) {
    if (score >= 60) return "sb";
    if (score >= 25) return "b";
    if (score <= -60) return "ss";
    if (score <= -25) return "s";
    return "n";
  },

  badgeMeasure(label, cls) {
    const span = document.createElement("span");
    span.className = "h-badge " + cls;
    span.textContent = label;
    return span;
  },

  pill(text, cls) {
    const span = document.createElement("span");
    span.className = "pill" + (cls ? " " + cls : "");
    span.textContent = text;
    return span;
  },

  scoreBar(score, cls) {
    const bar = this.el("div", "score-bar" + (cls ? " " + cls : ""));
    const fill = this.el("div", "score-fill " + (score >= 0 ? "score-pos" : "score-neg"));
    fill.style.width = this.clamp(Math.abs(score), 0, 100) + "%";
    bar.title = this.fmt(score);
    bar.appendChild(fill);
    return bar;
  },

  confBar(conf) {
    const bar = this.el("div", "conf-bar");
    const fill = this.el("div", "conf-fill");
    fill.style.width = this.clamp(conf, 0, 100) + "%";
    bar.appendChild(fill);
    return bar;
  },

  signalStrip(signals, HORDER) {
    const strip = this.el("div", "signal-strip");
    for (const h of HORDER) {
      const sig = (signals || []).find((s) => s.horizon === h);
      const cell = this.el("span", "strip-cell");
      if (sig) {
        const action = this.actionFor(sig.score);
        const dir = sig.score > 0 ? "up" : (sig.score < 0 ? "down" : "flat");
        const p = sig.probability_up * 100;
        const conf = sig.confidence === undefined ? 0 : sig.confidence;
        cell.title = h + " " + this.actionFor(sig.score) + " " + this.fmt(p, 0) + "% · " + this.fmt(conf, 0) + "%";
        const bar = this.el("i", "strip-bar " + action + " " + dir);
        bar.style.height = this.clamp(Math.abs(sig.score), 0, 100) + "%";
        cell.appendChild(bar);
      } else {
        cell.title = h + " ·";
      }
      strip.appendChild(cell);
    }
    return strip;
  }
};
