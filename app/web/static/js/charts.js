window.TA = window.TA || {};

TA.charts = {
  _alpha(c, a) {
    var m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(c); if (!m) return null;
    var h = m[1]; if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    return "rgba(" + (n >> 16 & 255) + "," + (n >> 8 & 255) + "," + (n & 255) + "," + a + ")";
  },
  _clear(canvas) {
    if (!canvas) return false;
    canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
    return false;
  },
  _prep(canvas, h) {
    var p = canvas.parentElement, w = p && p.clientWidth > 0 ? p.clientWidth : 120;
    var hh = h > 0 ? h : 36, dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(hh * dpr);
    canvas.style.width = w + "px"; canvas.style.height = hh + "px";
    var ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, hh);
    return [w, hh, ctx];
  },
  _pts(data, w, h) {
    var n = data.length, mx = data[0], mn = data[0], i, pad = 2;
    for (i = 1; i < n; i++) if (data[i] > mx) mx = data[i]; else if (data[i] < mn) mn = data[i];
    var span = mx - mn || 1, pw = w - pad * 2, ph = h - pad * 2, pts = new Array(n);
    for (i = 0; i < n; i++) pts[i] = { x: pad + (i / (n - 1)) * pw, y: pad + (1 - (data[i] - mn) / span) * ph };
    return pts;
  },
  _trace(ctx, pts) {
    ctx.moveTo(pts[0].x, pts[0].y);
    for (var i = 0; i < pts.length - 1; i++) {
      var p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
      ctx.bezierCurveTo(p1.x + (p2.x - p0.x) / 6, p1.y + (p2.y - p0.y) / 6,
        p2.x - (p3.x - p1.x) / 6, p2.y - (p3.y - p1.y) / 6, p2.x, p2.y);
    }
  },
  sparkline(canvas, values, opts) {
    opts = opts || {};
    if (!canvas || !Array.isArray(values) || values.length < 2) return this._clear(canvas);
    var data = [], i;
    for (i = 0; i < values.length; i++) if (typeof values[i] === "number" && isFinite(values[i])) data.push(values[i]);
    if (data.length < 2) return this._clear(canvas);
    var dim = this._prep(canvas, opts.height); if (!dim) return this._clear(canvas);
    var w = dim[0], h = dim[1], ctx = dim[2], pts = this._pts(data, w, h), n = data.length;
    var color = opts.color;
    if (opts.up !== undefined || opts.down !== undefined)
      color = data[n - 1] >= data[0] ? (opts.up || color) : (opts.down || color);
    if (!color) color = "#38bdf8";
    if (opts.fill) {
      var fo = typeof opts.fill === "number" ? opts.fill : 0.2, ra = this._alpha(color, fo);
      ctx.fillStyle = color;
      if (ra) {
        var g = ctx.createLinearGradient(0, 0, 0, h);
        g.addColorStop(0, ra);
        g.addColorStop(1, this._alpha(color, 0));
        ctx.fillStyle = g;
      } else {
        ctx.globalAlpha = fo;
      }
      ctx.beginPath();
      this._trace(ctx, pts);
      ctx.lineTo(pts[n - 1].x, h - 2); ctx.lineTo(pts[0].x, h - 2);
      ctx.closePath();
      ctx.fill();
      if (!ra) ctx.globalAlpha = 1;
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = opts.strokeWidth || 1.5;
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    ctx.beginPath(); this._trace(ctx, pts); ctx.stroke();
    return true;
  },
  gauge(target, p01, opts) {
    if (!target) return null;
    opts = opts || {};
    var p = typeof p01 === "number" && isFinite(p01) ? Math.min(1, Math.max(0, p01)) : 0;
    var size = opts.size || 96, stroke = opts.stroke || 10, NS = "http://www.w3.org/2000/svg";
    var r = (size - stroke) / 2, c = size / 2, C = 2 * Math.PI * r;
    var wrap = document.createElement("div");
    wrap.className = "gauge-wrap";
    wrap.setAttribute("aria-hidden", "true");
    var mk = function (el, attrs) {
      var e = document.createElementNS(NS, el);
      for (var k in attrs) e.setAttribute(k, attrs[k]);
      return e;
    };
    var svg = mk("svg", { viewBox: "0 0 " + size + " " + size, width: size, height: size });
    svg.appendChild(mk("circle", { cx: c, cy: c, r: r, fill: "none", stroke: "var(--track)", "stroke-width": stroke }));
    var color = p < 0.35 ? "var(--down)" : p > 0.65 ? "var(--up)" : "var(--accent)";
    svg.appendChild(mk("circle", {
      cx: c, cy: c, r: r, fill: "none", stroke: color, "stroke-width": stroke,
      "stroke-linecap": "round", "stroke-dasharray": C + " " + C,
      "stroke-dashoffset": C * (1 - p), transform: "rotate(-90 " + c + " " + c + ")"
    }));
    var txt = mk("text", { x: c, y: c, "text-anchor": "middle", "dominant-baseline": "central",
      fill: "var(--text-strong)", "font-size": Math.round(size / 4), "font-weight": 700 });
    txt.textContent = Math.round(p * 100) + "%";
    svg.appendChild(txt);
    if (opts.label) {
      var lbl = mk("text", { x: c, y: c + Math.round(size / 5), "text-anchor": "middle",
        fill: "var(--text-soft)", "font-size": Math.round(size / 8.5) });
      lbl.textContent = String(opts.label);
      svg.appendChild(lbl);
    }
    if (opts.tick) {
      var tk = mk("text", { x: c, y: c + Math.round(size / 3), "text-anchor": "middle",
        fill: "var(--text-faint)", "font-size": Math.round(size / 10) });
      tk.textContent = String(opts.tick);
      svg.appendChild(tk);
    }
    wrap.appendChild(svg);
    target.innerHTML = "";
    target.appendChild(wrap);
    return wrap;
  },
  bars(canvas, values, opts) {
    opts = opts || {};
    if (!canvas || !Array.isArray(values) || !values.length) return this._clear(canvas);
    var data = [], i;
    for (i = 0; i < values.length; i++) if (typeof values[i] === "number" && isFinite(values[i])) data.push(values[i]);
    if (!data.length) return this._clear(canvas);
    var dim = this._prep(canvas, opts.height); if (!dim) return false;
    var w = dim[0], h = dim[1], ctx = dim[2];
    var n = data.length, m = 0, j, abs = new Array(n);
    for (j = 0; j < n; j++) { abs[j] = Math.abs(data[j]); if (abs[j] > m) m = abs[j]; }
    if (!(m > 0)) return this._clear(canvas);
    var up = opts.color || "#10b981", down = opts.downColor || "#f43f5e", bw = w / n;
    for (j = 0; j < n; j++) {
      var bh = (abs[j] / m) * (h - 2);
      ctx.fillStyle = data[j] >= 0 ? up : down;
      ctx.fillRect(j * bw + 0.5, h - bh, Math.max(1, bw - 1), bh);
    }
    return true;
  }
};