window.TA = window.TA || {};

TA.panels = TA.panels || {};

(function () {
  const INTERVAL = 60000;

  async function loadConsensus() {
    try {
      const res = await fetch("/api/consensus");
      if (!res.ok) throw new Error("consensus " + res.status);
      const data = await res.json();
      if (TA.panels.renderConsensus) TA.panels.renderConsensus(data);
    } catch (e) {
      console.warn("[consensus-fetch]", e);
    }
  }

  async function loadAccuracy() {
    try {
      const res = await fetch("/api/accuracy");
      if (!res.ok) throw new Error("accuracy " + res.status);
      const data = await res.json();
      if (TA.panels.renderAccuracy) TA.panels.renderAccuracy(data);
    } catch (e) {
      console.warn("[consensus-fetch]", e);
    }
  }

  function tick() {
    loadConsensus();
    loadAccuracy();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", tick);
  } else {
    tick();
  }

  setInterval(tick, INTERVAL);
})();
