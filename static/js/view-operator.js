window.SlipformOperatorView = (() => {
  const { $, state } = window.SlipformApp;
  const { escapeHtml, format } = window.SlipformUtils;

  function echart() {
    return window.SlipformECharts || null;
  }

  function renderZoneSelectors(zones) {
    const zoneReading = $("#zone-reading-select");
    if (!zoneReading) return;
    zoneReading.innerHTML =
      zones.length === 0
        ? `<option value="">Registra ollas primero</option>`
        : zones
            .map(
              (zone) =>
                `<option value="${escapeHtml(zone.id)}">Zona ${escapeHtml(zone.zona_numero)} - ${format(
                  zone.elevacion_inferior_cm,
                  0
                )}-${format(zone.elevacion_superior_cm, 0)} cm</option>`
            )
            .join("");
  }

  function renderReadings(readings) {
    const table = $("#readings-table");
    if (!table) return;
    const latest = readings.slice(-30).reverse();
    table.innerHTML =
      latest.length === 0
        ? `<tr><td colspan="5">Sin lecturas.</td></tr>`
        : latest
            .map(
              (reading) => `<tr>
                <td>${format(reading.minuto_transcurrido, 1)}</td>
                <td>${format(reading.temperatura_concreto_c, 1)} C</td>
                <td>${format(reading.temperatura_ambiente_c, 1)} C</td>
                <td>${format(reading.humedad_relativa_pct, 1)}%</td>
                <td>${escapeHtml(reading.origen || "")}</td>
              </tr>`
            )
            .join("");
  }

  function renderOperatorLiveTrend(result) {
    const target = $("#operator-temperature-trend");
    if (!target) return;
    const temp = result?.temperatura || {};
    const current = temp.actual;
    const delta = temp.diferencia_vs_esperada_c;
    const source = temp.origen_actual || current?.origen || "sin_datos";
    const deltaTarget = $("#operator-temperature-delta");
    const sourceTarget = $("#operator-temperature-source");
    if (deltaTarget) {
      deltaTarget.textContent = current
        ? delta == null
          ? `${format(current.temperatura_concreto_c, 1)} C actual`
          : `${format(delta, 1)} C vs esperada`
        : "Captura temperatura";
    }
    if (sourceTarget) sourceTarget.textContent = `Fuente: ${source.replaceAll("_", " ")}`;
    renderOperatorMaturityEta(result);
    renderOperatorZoneStatus(result);
    if (echart()?.renderTemperature("#operator-temperature-trend", result, true)) return;
    target.innerHTML = `<div class="empty-chart">Captura temperatura para iniciar tendencia.</div>`;
  }

  function renderOperatorZoneStatus(result) {
    const target = $("#operator-zone-status-list");
    if (!target) return;
    const zones = (result?.resumen_zonas || []).slice().sort((a, b) => Number(a.zona_numero || 0) - Number(b.zona_numero || 0));
    const selectedId = String(result?.zona?.id || state.moldState?.zona_en_liberacion?.id || "");
    if (!zones.length) {
      target.innerHTML = `<div class="operator-zone-status-empty">Registra ollas para ver el estado de zonas.</div>`;
      return;
    }
    target.innerHTML = zones
      .map((zone) => {
        const remaining = Number(zone.minutos_restantes_deslizar);
        const eta = zone.hora_liberacion_campo
          ? `Lista por criterio ${shortTime(zone.hora_liberacion_campo)}`
          : zone.es_zona_heredada
            ? "Lista por campo"
            : zone.hora_estimada_deslizar_ajustada
              ? `Ajuste campo ${shortTime(zone.hora_estimada_deslizar_ajustada)}`
              : zone.confianza === "insuficiente"
                ? "Sin estimacion confiable"
                : remaining <= 0
                  ? `Lista desde ${shortTime(zone.hora_estimada_deslizar)}`
                  : `Lista aprox. ${shortTime(zone.hora_estimada_deslizar)}`;
        const adjustment = zone.hora_estimada_deslizar_ajustada
          ? `<small class="zone-status-adjusted">Arrhenius ${escapeHtml(shortTime(zone.hora_estimada_deslizar))} | Ajuste campo ${escapeHtml(
              shortTime(zone.hora_estimada_deslizar_ajustada)
            )}</small>`
          : "";
        return `<article class="operator-zone-status-card ${operatorZoneTone(zone)} ${
          String(zone.id) === selectedId ? "selected" : ""
        }" data-zone-id="${escapeHtml(zone.id)}">
          <strong>Zona ${escapeHtml(zone.zona_numero)}</strong>
          <span>${
            zone.es_zona_heredada
              ? "Existente previo | Sin olla"
              : `Olla ${escapeHtml(zone.numero_olla || zone.zona_numero || "--")} | Salida ${escapeHtml(shortTime(zone.hora_salida_planta))}`
          }</span>
          <small class="zone-status-meta">Madurez ${format(zone.madurez_actual_pct, 1)}% | Temp. ${
            zone.temperatura_actual_c == null ? "-- C" : `${format(zone.temperatura_actual_c, 1)} C`
          }</small>
          <small class="zone-status-source">Fuente ${escapeHtml((zone.fuente_temperatura || "sin_datos").replaceAll("_", " "))}</small>
          <small class="zone-status-eta">${escapeHtml(eta)} | ${escapeHtml(remainingText(zone.minutos_restantes_deslizar))}</small>
          ${adjustment}
          <small class="zone-status-chip">${escapeHtml(operatorZoneStatusLabel(zone))}</small>
          <button type="button" class="button-small secondary zone-temperature-action" data-zone-id="${escapeHtml(zone.id)}">
            Capturar temp.
          </button>
        </article>`;
      })
      .join("");
    target.querySelectorAll(".operator-zone-status-card").forEach((card) => {
      card.addEventListener("click", (event) => {
        if (event.target.closest(".zone-temperature-action")) return;
        openOperatorZone(card.dataset.zoneId || "");
      });
    });
    target.querySelectorAll(".zone-temperature-action").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        window.saveOperatorZoneTemperature?.(button.dataset.zoneId || "");
      });
    });
  }

  function openOperatorZone(zoneId) {
    document.querySelectorAll(".operator-zone-status-card").forEach((card) => {
      card.classList.toggle("selected", card.dataset.zoneId === String(zoneId || ""));
    });
  }

  function operatorZoneTone(zone) {
    if (zone.es_zona_heredada) return "ready field-ready";
    if (zone.hora_liberacion_campo || zone.confianza === "criterio_campo" || zone.madurez_fuente === "criterio_campo") {
      return "ready field-ready";
    }
    if (zone.confianza === "insuficiente") return "insufficient";
    const maturity = Number(zone.madurez_actual_pct);
    const status = String(zone.estado_zona || "").toUpperCase();
    if (status.includes("NO_LIBERAR") || maturity < 70) return "blocked";
    if (status.includes("RIESGO") || maturity > 105) return "risk";
    if (maturity >= 90 || Number(zone.minutos_restantes_deslizar) <= 0) return "ready";
    return "residence";
  }

  function operatorZoneStatusLabel(zone) {
    if (zone.es_zona_heredada) return "Existente previo";
    if (zone.hora_liberacion_campo || zone.confianza === "criterio_campo" || zone.madurez_fuente === "criterio_campo") {
      return "Criterio campo";
    }
    if (zone.confianza === "insuficiente") return "Sin estimacion";
    const status = String(zone.estado_zona || "").toUpperCase();
    const maturity = Number(zone.madurez_actual_pct);
    if (status.includes("NO_LIBERAR") || maturity < 70) return "No liberar";
    if (status.includes("RIESGO") || maturity > 105) return "Riesgo";
    if (maturity >= 90 || Number(zone.minutos_restantes_deslizar) <= 0) return "Lista";
    return "Residencia";
  }

  function renderOperatorMaturityEta(result) {
    const target = $("#operator-maturity-eta");
    if (!target) return;
    const prediction = result?.zona_prediccion || {};
    const zoneNumber = prediction.zona_numero || result?.zona?.zona_numero || state.moldState?.zona_en_liberacion?.zona_numero;
    if (!prediction.hora_estimada_deslizar) {
      target.textContent = "Estimacion de madurez: sin estimacion confiable.";
      target.className = "operator-maturity-eta insufficient";
      return;
    }
    const remaining = Number(prediction.minutos_restantes_deslizar);
    const label = remaining <= 0 ? "Lista para evaluar" : `faltan ${format(remaining, 0)} min`;
    const adjusted = prediction.hora_estimada_deslizar_ajustada
      ? ` | Ajuste campo: ${shortTime(prediction.hora_estimada_deslizar_ajustada)}`
      : "";
    target.textContent = `Zona ${zoneNumber || "--"} Arrhenius: ${shortTime(prediction.hora_estimada_deslizar)} | ${label}${adjusted}`;
    target.className = `operator-maturity-eta ${remaining <= 0 ? "ready" : "pending"}`;
  }

  function remainingText(minutes) {
    if (minutes == null || !Number.isFinite(Number(minutes))) return "Sin estimacion";
    const value = Number(minutes);
    if (value <= 0) return "Lista para evaluar";
    if (value < 60) return `${format(value, 0)} min`;
    return `${format(value / 60, 1)} h`;
  }

  function shortTime(value) {
    if (!value) return "--";
    const date = new Date(value);
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
    }
    const text = String(value);
    return text.includes("T") ? text.split("T")[1].slice(0, 5) : text.slice(11, 16) || text;
  }

  return {
    renderOperatorLiveTrend,
    renderOperatorMaturityEta,
    renderOperatorZoneStatus,
    renderReadings,
    renderZoneSelectors,
  };
})();
