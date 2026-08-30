window.TA = window.TA || {};

function alertKey(a) {
  return ((a && a.ts) || "") + "|" + ((a && a.symbol) || "") + "|" + ((a && a.kind) || "");
}

TA.alerts = {
  kindClass(kind) {
    if (kind === "PREDICTION_SUCCESS") return "success";
    if (kind === "PREDICTION_WRONG") return "wrong";
    return "miss";
  },

  render(list) {
    const items = list === undefined ? TA.state.alerts : list;
    if (!Array.isArray(items)) return;
    const panel = document.getElementById("alerts-panel");
    const listEl = document.getElementById("alerts-list");
    const countEl = document.getElementById("alerts-count");
    const emptyEl = document.getElementById("alerts-empty");
    if (listEl) {
      listEl.innerHTML = "";
      items.forEach((a) => listEl.appendChild(this._item(a)));
    }
    if (countEl) countEl.textContent = String(items.length);
    if (panel) panel.classList.toggle("hidden", items.length === 0);
    if (emptyEl) emptyEl.style.display = items.length === 0 ? "block" : "none";
  },

  _item(alert) {
    const item = document.createElement("div");
    const kind = this.kindClass(alert && alert.kind);
    item.className = "alert-item alert-" + kind;
    item.dataset.key = alertKey(alert);

    const icon = document.createElement("span");
    icon.className = "alert-icon";
    icon.textContent = kind === "success" ? "\u2713" : (kind === "wrong" ? "\u2715" : "\u2022");
    item.appendChild(icon);

    const label = document.createElement("div");
    label.className = "alert-label";
    const title = document.createElement("span");
    title.className = "alert-title";
    title.textContent = [
      alert.name || alert.symbol || "-",
      alert.horizon || "-",
      alert.action || "-"
    ].join(" \u00b7 ");
    label.appendChild(title);
    const time = document.createElement("span");
    time.className = "alert-time mono";
    time.textContent = TA.utils.fmtTime(alert.ts);
    label.appendChild(time);
    item.appendChild(label);

    if (alert.message) {
      const msg = document.createElement("div");
      msg.className = "alert-msg";
      msg.textContent = alert.message;
      item.appendChild(msg);
    }

    const meta = document.createElement("div");
    meta.className = "alert-meta";
    if (alert.actual_return !== undefined && alert.actual_return !== null && !isNaN(alert.actual_return)) {
      const chip = document.createElement("span");
      chip.className = "alert-return " + (alert.actual_return >= 0 ? "pos" : "neg");
      chip.textContent = TA.utils.fmtPctNum(alert.actual_return);
      meta.appendChild(chip);
    }
    if (alert.probability !== undefined && alert.probability !== null) {
      meta.appendChild(TA.utils.pill("P " + alert.probability + "%", "pill-muted"));
    }
    if (alert.entry_price !== undefined && alert.entry_price !== null && !isNaN(alert.entry_price)) {
      meta.appendChild(TA.utils.pill("entry " + TA.utils.fmt(alert.entry_price), "pill-muted"));
    }
    if (alert.exit_price !== undefined && alert.exit_price !== null && !isNaN(alert.exit_price)) {
      meta.appendChild(TA.utils.pill("exit " + TA.utils.fmt(alert.exit_price), "pill-muted"));
    }
    item.appendChild(meta);

    return item;
  },

  add(alert) {
    if (!alert) return;
    const key = alertKey(alert);
    const list = TA.state.alerts || (TA.state.alerts = []);
    const dup = list.some((x) => alertKey(x) === key);
    if (!dup) list.unshift(alert);
    this.render();
    let flashEl = null;
    document.querySelectorAll("#alerts-list .alert-item").forEach((n) => {
      if (n.dataset.key === key) flashEl = n;
    });
    if (flashEl) flashEl.classList.add("flash");
  },

  clear() {
    TA.state.alerts = [];
    this.render();
  },

  toggleCollapse() {
    const panel = document.getElementById("alerts-panel");
    if (!panel) return;
    const collapsed = panel.classList.toggle("collapsed");
    const btn = document.getElementById("alerts-toggle");
    if (btn) btn.textContent = collapsed ? "Expand" : "Collapse";
  },

  toggle() {
    this.toggleCollapse();
  }
};