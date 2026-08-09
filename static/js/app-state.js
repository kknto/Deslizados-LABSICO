window.SlipformApp = (() => {
  const state = {
    bootstrap: JSON.parse(localStorage.getItem("bootstrap") || "{}"),
    activeColadoId: localStorage.getItem("activeColadoId") || "",
    offlineQueue: JSON.parse(localStorage.getItem("offlineQueue") || "[]"),
    localReadings: JSON.parse(localStorage.getItem("localReadings") || "{}"),
    latestPrediction: null,
    moldState: null,
    scadaState: null,
    trends: null,
    schedule: null,
    dataQuality: null,
    operationalData: {
      turnos: [],
      fotografias: [],
      desplomes: [],
      ajustes: [],
      sensores: [],
      descargas: [],
    },
    diagnostics: null,
    lastMoldBaseCm: null,
    lastMoldColadoId: null,
    previousMoldBaseCm: null,
    lastMoldMoveCm: 0,
    evaluationTime: localStorage.getItem("evaluationTime") || "",
  };

  const $ = (selector) => document.querySelector(selector);

  function setConnection(text, ok = true) {
    const el = $("#connection");
    if (!el) return;
    el.textContent = text;
    el.style.background = ok ? "#dcfce7" : "#fee2e2";
    el.style.color = ok ? "#147a4d" : "#b42318";
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!response.ok) {
      const text = await response.text();
      let body = null;
      try {
        body = text ? JSON.parse(text) : null;
      } catch (_) {
        body = null;
      }
      const error = new Error(body?.error || text || `HTTP ${response.status}`);
      error.status = response.status;
      error.body = body;
      throw error;
    }
    return response.headers.get("content-type")?.includes("application/json")
      ? response.json()
      : response.text();
  }

  return { $, api, setConnection, state };
})();
