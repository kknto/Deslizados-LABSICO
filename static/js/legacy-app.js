const { $, api, setConnection, state } = window.SlipformApp;
const {
  escapeHtml,
  format,
  formatBytes,
  formatDatetimeLocal,
  moldStateClass,
  stateClass,
  toDatetimeLocalValue,
} = window.SlipformUtils;
const { drawAxes, drawEmptyChart, drawLine, drawThreshold } = window.SlipformCharts;

const DEFAULT_ADVANCE_CM = 3.0;
const DEFAULT_ADVANCE_INTERVAL_MIN = 6.0;
const DEFAULT_ADVANCE_SPEED_CM_H = DEFAULT_ADVANCE_CM / (DEFAULT_ADVANCE_INTERVAL_MIN / 60);

state.localInspectionSignals = state.localInspectionSignals || JSON.parse(localStorage.getItem("localInspectionSignals") || "{}");

function setupTabs() {
  const buttons = [...document.querySelectorAll(".tab-button")];
  const panels = [...document.querySelectorAll(".tab-panel")];
  buttons.forEach((button) => {
    const tabName = button.dataset.tab;
    button.id = button.id || `tab-button-${tabName}`;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-controls", `tab-${tabName}`);
    button.setAttribute("aria-selected", button.classList.contains("active") ? "true" : "false");
    button.tabIndex = button.classList.contains("active") ? 0 : -1;
    button.addEventListener("click", () => {
      activateTab(tabName, { focus: false });
    });
    button.addEventListener("keydown", (event) => {
      const current = buttons.indexOf(button);
      const keys = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
      if (event.key === "Home") {
        event.preventDefault();
        activateTab(buttons[0].dataset.tab, { focus: true });
      } else if (event.key === "End") {
        event.preventDefault();
        activateTab(buttons[buttons.length - 1].dataset.tab, { focus: true });
      } else if (event.key in keys) {
        event.preventDefault();
        const next = (current + keys[event.key] + buttons.length) % buttons.length;
        activateTab(buttons[next].dataset.tab, { focus: true });
      }
    });
  });
  panels.forEach((panel) => {
    const tabName = panel.id.replace("tab-", "");
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", `tab-button-${tabName}`);
    panel.tabIndex = 0;
    panel.hidden = !panel.classList.contains("active");
  });
}

function activateTab(tabName, options = {}) {
  document.querySelectorAll(".tab-button").forEach((item) => {
    const active = item.dataset.tab === tabName;
    item.classList.toggle("active", active);
    item.setAttribute("aria-selected", active ? "true" : "false");
    item.tabIndex = active ? 0 : -1;
    if (active && options.focus) item.focus();
  });
  document.querySelectorAll(".tab-panel").forEach((item) => {
    const active = item.id === `tab-${tabName}`;
    item.classList.toggle("active", active);
    item.hidden = !active;
  });
  const panel = $(`#tab-${tabName}`);
  if (tabName === "operador") refreshOperatorStateSilently();
  if (tabName === "tendencias") refreshTrends();
  if (tabName === "programa") refreshSlipSchedule();
  setTimeout(() => window.SlipformECharts?.resizeAll(), 50);
  if (["reportes", "evidencia", "sensores", "calibracion"].includes(tabName)) refreshOperationalData();
  if (tabName === "diagnostico") refreshDiagnostics();
}

function showAppNotice(message, type = "info") {
  const region = $("#app-notifications");
  if (!region) return;
  region.innerHTML = `<div class="app-notice ${escapeHtml(type)}">${escapeHtml(message)}</div>`;
  window.clearTimeout(showAppNotice.timer);
  showAppNotice.timer = window.setTimeout(() => {
    region.innerHTML = "";
  }, 7000);
}

function appDialog({ title = "Mensaje del sistema", message = "", type = "info", confirmText = "Aceptar", cancelText = "", promptLabel = "", promptValue = "" }) {
  const backdrop = $("#app-dialog");
  if (!backdrop) return Promise.resolve(promptLabel ? promptValue : true);
  const titleEl = $("#app-dialog-title");
  const messageEl = $("#app-dialog-message");
  const kickerEl = $("#app-dialog-kicker");
  const inputRow = $("#app-dialog-input-row");
  const input = $("#app-dialog-input");
  const confirmBtn = $("#app-dialog-confirm");
  const cancelBtn = $("#app-dialog-cancel");
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      backdrop.hidden = true;
      document.body.classList.remove("app-dialog-open");
      backdrop.className = "app-dialog-backdrop";
      confirmBtn.removeEventListener("click", onConfirm);
      cancelBtn.removeEventListener("click", onCancel);
      backdrop.removeEventListener("click", onBackdrop);
      document.removeEventListener("keydown", onKeydown);
      resolve(value);
    };
    const onConfirm = () => finish(promptLabel ? input.value : true);
    const onCancel = () => finish(promptLabel ? null : false);
    const onBackdrop = (event) => {
      if (event.target === backdrop) onCancel();
    };
    const onKeydown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
      }
      if (event.key === "Enter" && promptLabel && document.activeElement === input) {
        event.preventDefault();
        onConfirm();
      }
    };

    titleEl.textContent = title;
    messageEl.textContent = String(message || "");
    kickerEl.textContent = type === "danger" || type === "error" ? "Accion critica" : type === "warning" ? "Confirmacion operativa" : "Aviso operativo";
    confirmBtn.textContent = confirmText;
    cancelBtn.textContent = cancelText || "Cancelar";
    cancelBtn.hidden = !cancelText;
    inputRow.hidden = !promptLabel;
    inputRow.style.display = promptLabel ? "" : "none";
    input.disabled = !promptLabel;
    if (promptLabel) {
      inputRow.childNodes[0].nodeValue = `${promptLabel} `;
      input.value = promptValue || "";
    } else {
      input.value = "";
    }
    backdrop.className = `app-dialog-backdrop dialog-${type}`;
    backdrop.classList.toggle("has-prompt", Boolean(promptLabel));
    backdrop.hidden = false;
    document.body.classList.add("app-dialog-open");
    confirmBtn.addEventListener("click", onConfirm);
    cancelBtn.addEventListener("click", onCancel);
    backdrop.addEventListener("click", onBackdrop);
    document.addEventListener("keydown", onKeydown);
    setTimeout(() => (promptLabel ? input : confirmBtn).focus(), 0);
  });
}

function appAlert(message, options = {}) {
  return appDialog({
    title: options.title || (options.type === "error" ? "No se pudo completar" : "Aviso del sistema"),
    message,
    type: options.type || "info",
    confirmText: options.confirmText || "Entendido",
  });
}

function appConfirm(message, options = {}) {
  return appDialog({
    title: options.title || "Confirmar accion",
    message,
    type: options.type || "warning",
    confirmText: options.confirmText || "Continuar",
    cancelText: options.cancelText || "Cancelar",
  });
}

function appPrompt(message, defaultValue = "", options = {}) {
  return appDialog({
    title: options.title || "Dato requerido",
    message,
    type: options.type || "warning",
    confirmText: options.confirmText || "Aceptar",
    cancelText: options.cancelText || "Cancelar",
    promptLabel: options.promptLabel || "Valor",
    promptValue: defaultValue,
  });
}

window.alert = (message) => {
  appAlert(String(message || ""));
};

function setupFormValidation() {
  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener(
      "invalid",
      (event) => {
        event.preventDefault();
        markInvalidField(event.target);
      },
      true
    );
    form.addEventListener("input", (event) => clearInvalidField(event.target), true);
    form.addEventListener("change", (event) => clearInvalidField(event.target), true);
    form.addEventListener("submit", (event) => {
      clearFormErrors(form);
      if (form.checkValidity()) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const invalid = [...form.elements].filter((element) => element.willValidate && !element.validity.valid);
      invalid.forEach(markInvalidField);
      showAppNotice("Revisa los campos marcados antes de continuar.", "error");
      invalid[0]?.focus();
    });
  });
}

function markInvalidField(field) {
  if (!field || !field.setAttribute) return;
  field.setAttribute("aria-invalid", "true");
  const label = field.closest("label");
  const existing = label?.querySelector(".field-error");
  const message = field.validationMessage || "Dato requerido o invalido.";
  if (label && !existing) {
    const error = document.createElement("span");
    error.className = "field-error";
    error.textContent = message;
    label.appendChild(error);
  } else if (existing) {
    existing.textContent = message;
  }
}

function clearInvalidField(field) {
  if (!field || !field.removeAttribute || field.validity?.valid === false) return;
  field.removeAttribute("aria-invalid");
  field.closest("label")?.querySelector(".field-error")?.remove();
}

function clearFormErrors(form) {
  form.querySelectorAll("[aria-invalid='true']").forEach((field) => field.removeAttribute("aria-invalid"));
  form.querySelectorAll(".field-error").forEach((error) => error.remove());
}

async function loadBootstrap() {
  try {
    state.bootstrap = await api("/api/bootstrap");
    normalizeActiveColado();
    localStorage.setItem("bootstrap", JSON.stringify(state.bootstrap));
    setConnection("En linea", true);
  } catch (error) {
    setConnection("Sin conexion", false);
  }
  renderSelectors();
  renderProjectForm();
  await refreshPrediction();
  await refreshMoldState();
  await refreshSlipSchedule();
  await refreshOperationalData();
  await refreshDiagnostics();
}

function setupEvaluationTime() {
  const input = $("#evaluation-time");
  if (input) input.value = state.evaluationTime;
  updateEvaluationHint();
  applyFieldMode();
}

function updateEvaluationHint(serverTime = "") {
  const hint = $("#evaluation-hint");
  const fieldTime = $("#field-command-time");
  if (!hint) return;
  if (state.evaluationTime) {
    hint.textContent = `Calculando contra ${state.evaluationTime.replace("T", " ")}.`;
    if (fieldTime) fieldTime.textContent = state.evaluationTime.replace("T", " ");
    const inline = $("#time-inline");
    if (inline) inline.textContent = state.evaluationTime.replace("T", " ");
  } else if (serverTime) {
    hint.textContent = `Calculando con hora real: ${serverTime.replace("T", " ")}.`;
    if (fieldTime) fieldTime.textContent = serverTime.replace("T", " ");
    const inline = $("#time-inline");
    if (inline) inline.textContent = serverTime.replace("T", " ");
  } else {
    hint.textContent = "Calculando con hora real.";
    if (fieldTime) fieldTime.textContent = "Hora real";
    const inline = $("#time-inline");
    if (inline) inline.textContent = "Hora real";
  }
}

function applyFieldMode() {
  const mode = localStorage.getItem("scadaViewMode") || "campo";
  const isField = mode !== "diagnostico";
  document.body.classList.toggle("field-mode", isField);
  document.body.classList.toggle("scada-mode-campo", isField);
  document.body.classList.toggle("scada-mode-diagnostico", !isField);
  const button = $("#field-mode-toggle");
  if (button) button.textContent = isField ? "Ver Diagnostico" : "Modo Campo";
  const label = $("#scada-mode-label");
  if (label) label.textContent = isField ? "Campo" : "Diagnostico";
  document.querySelectorAll(".scada-detail").forEach((detail) => {
    detail.open = !isField;
  });
}

function setFieldCommandState(result) {
  const status = result?.estado_operativo || "SIN_ZONAS";
  const alarms = state.scadaState?.alarmas_activas || [];
  const commandState = $("#field-command-state");
  const commandZone = $("#field-command-zone");
  const commandTemp = $("#field-command-temp");
  const commandAlarm = $("#field-command-alarm");
  const criticalBanner = $("#critical-alarm-banner");
  const criticalAlarm = alarms.find((alarm) => ["CRITICA", "ALTA"].includes(String(alarm.severidad || "").toUpperCase()));
  if (commandState) {
    commandState.textContent = status.replaceAll("_", " ");
    commandState.className = `field-state ${moldStateClass(status)}`;
  }
  if (commandZone) {
    const zone = result?.zona_en_liberacion?.zona_numero;
    commandZone.textContent = zone ? `Zona ${zone}` : "--";
  }
  if (commandTemp) {
    const temp = result?.zona_en_liberacion?.temperatura_actual_c;
    commandTemp.textContent = temp == null ? "-- C" : `${format(temp, 1)} C`;
  }
  if (commandAlarm) commandAlarm.textContent = alarms.length ? `${alarms.length} activa(s)` : "Sin alarmas";
  if (criticalBanner) {
    criticalBanner.textContent = criticalAlarm ? criticalAlarm.mensaje || criticalAlarm.tipo : "Sin alarmas criticas.";
    criticalBanner.classList.toggle("active", Boolean(criticalAlarm));
  }
  updateInspectionSignal();
}

function updateCaptureReadiness() {
  const colado = activeColado();
  const zones = state.moldState?.zonas_activas || [];
  const recipe = state.moldState?.receta_avance || null;
  const readings = state.latestPrediction?.lecturas || [];
  const setReady = (selector, ready, text) => {
    const el = $(selector);
    if (!el) return;
    el.classList.toggle("ready", Boolean(ready));
    el.classList.toggle("pending", !ready);
    const strong = el.querySelector?.("strong");
    if (strong) strong.textContent = text;
  };
  setReady("#capture-ready-colado", Boolean(colado), colado ? `#${colado.id}` : "Pendiente");
  setReady("#capture-ready-zones", zones.length > 0, zones.length ? `${zones.length} zonas` : "Pendiente");
  setReady("#capture-ready-recipe", Boolean(recipe), recipe ? `${format(recipe.avance_objetivo_cm, 1)} cm` : "Default");
  setReady("#capture-ready-reading", readings.length > 0, readings.length ? `${readings.length} lecturas` : "Pendiente");
}

function evaluationDate() {
  const value = state.evaluationTime || $("#evaluation-time")?.value || "";
  const date = value ? new Date(value) : new Date();
  return Number.isNaN(date.getTime()) ? new Date() : date;
}

function isRecentInspection(decision) {
  if (!decision || decision.decision_operador !== "INSPECCION_OK") return false;
  const when = new Date(decision.fecha_hora);
  if (Number.isNaN(when.getTime())) return false;
  const ageMin = Math.abs(evaluationDate() - when) / 60000;
  return ageMin <= 15;
}

function rememberLocalInspection(fechaHora, checklist) {
  if (!state.activeColadoId) return;
  state.localInspectionSignals[String(state.activeColadoId)] = {
    decision_operador: "INSPECCION_OK",
    fecha_hora: fechaHora,
    checklist,
    local: true,
  };
  localStorage.setItem("localInspectionSignals", JSON.stringify(state.localInspectionSignals));
}

function latestInspectionOk() {
  const localSignal = state.localInspectionSignals?.[String(state.activeColadoId)];
  if (isRecentInspection(localSignal)) return localSignal;
  const decisions = state.scadaState?.decisiones_recientes || [];
  return decisions.find(isRecentInspection);
}

function latestConditionEvent() {
  const events = state.latestPrediction?.eventos || [];
  const now = evaluationDate();
  return events
    .slice()
    .reverse()
    .find((event) => {
      if (!event.resultado_fisico) return false;
      const when = new Date(event.fecha_hora || "");
      if (Number.isNaN(when.getTime())) return true;
      return Math.abs(now - when) / 60000 <= 30;
    });
}

function latestTemperatureReading() {
  const readings = state.latestPrediction?.lecturas || [];
  return readings
    .slice()
    .filter((reading) => reading.temperatura_concreto_c != null)
    .sort((a, b) => {
      const at = new Date(a.fecha_hora || 0).getTime() || Number(a.minuto_transcurrido || 0);
      const bt = new Date(b.fecha_hora || 0).getTime() || Number(b.minuto_transcurrido || 0);
      return bt - at;
    })[0];
}

function quickChecklistPayload() {
  return {
    inspeccion_fisica: true,
    no_desmorona: Boolean($("#check-no-desmorona")?.checked),
    no_se_pega: Boolean($("#check-no-se-pega")?.checked),
    acabado_aceptable: Boolean($("#check-acabado")?.checked),
    sin_arrastre: Boolean($("#check-sin-arrastre")?.checked),
  };
}

function checklistAllOk(checklist = quickChecklistPayload()) {
  return Boolean(checklist.no_desmorona && checklist.no_se_pega && checklist.acabado_aceptable && checklist.sin_arrastre);
}

function markChecklistOk() {
  ["check-no-desmorona", "check-no-se-pega", "check-acabado", "check-sin-arrastre"].forEach((id) => {
    const input = $(`#${id}`);
    if (input) input.checked = true;
  });
}

function setQuickChecklistForResult(result) {
  const values = {
    "check-no-desmorona": result !== "desmorona",
    "check-no-se-pega": result !== "se_pega",
    "check-acabado": !["desmorona", "fisura"].includes(result),
    "check-sin-arrastre": result !== "arrastra",
  };
  for (const [id, checked] of Object.entries(values)) {
    const input = $(`#${id}`);
    if (input) input.checked = checked;
  }
  renderOperationalGuidance();
}

function setOperationStep(selector, stateName, detail) {
  const el = $(selector);
  if (!el) return;
  el.className = `operation-step ${stateName}`;
  const small = el.querySelector("small");
  if (small) small.textContent = detail;
}

function dataQualityIssues() {
  const issues = [];
  for (const issue of state.dataQuality?.issues || []) {
    issues.push({ level: issue.level || "warn", text: issue.message || issue.summary || issue.code || "Revision de calidad de datos." });
  }
  const mold = state.moldState;
  const scada = state.scadaState;
  const zone = mold?.zona_en_liberacion;
  const reading = latestTemperatureReading();
  const source = zone?.fuente_temperatura || scada?.metricas?.fuente_temperatura || "";
  const alarms = scada?.alarmas_activas || [];
  if (!activeColado()) issues.push({ level: "critical", text: "No hay colado activo." });
  if (!mold?.zonas_activas?.length) issues.push({ level: "critical", text: "Faltan zonas de 30 cm." });
  if (!reading && zone?.temperatura_actual_c == null) issues.push({ level: "critical", text: "Falta temperatura real del concreto." });
  if (reading?.fecha_hora) {
    const ageMin = Math.abs(evaluationDate() - new Date(reading.fecha_hora)) / 60000;
    if (ageMin > 20) issues.push({ level: "warn", text: `Ultima temperatura hace ${format(ageMin, 0)} min.` });
  }
  if (["curva_referencia", "estimado", "sin_datos"].includes(source)) {
    issues.push({ level: "warn", text: `Temperatura usada: ${source || "sin_datos"}.` });
  }
  if (!latestInspectionOk()) issues.push({ level: "warn", text: "Inspeccion fisica pendiente o vencida." });
  if (!latestConditionEvent()) issues.push({ level: "warn", text: "Condicion fisica reciente no registrada." });
  for (const alarm of alarms.filter((item) => ["CRITICA", "ALTA"].includes(String(item.severidad || "").toUpperCase())).slice(0, 2)) {
    issues.push({ level: "critical", text: alarm.mensaje || alarm.tipo });
  }
  return issues;
}

function renderDataQualityPanel(target, issues = dataQualityIssues()) {
  if (!target) return;
  target.className = `data-quality-panel ${issues.some((issue) => issue.level === "critical") ? "critical" : issues.length ? "warn" : "ok"}`;
  target.innerHTML = issues.length
    ? issues.slice(0, 5).map((issue) => `<span>${escapeHtml(issue.text)}</span>`).join("")
    : "<span>Sin alertas de datos.</span>";
}

function renderOperationalGuidance() {
  const mold = state.moldState;
  const status = mold?.estado_operativo || "SIN_ZONAS";
  const zone = mold?.zona_en_liberacion;
  const reading = latestTemperatureReading();
  const hasTemperature = Boolean(reading || zone?.temperatura_actual_c != null);
  const inspection = latestInspectionOk();
  const condition = latestConditionEvent();
  const canAdvance = ["CONTINUAR", "RIESGO_AGARROTAMIENTO"].includes(status);
  setOperationStep("#step-temperature", hasTemperature ? "ready" : "pending", hasTemperature ? "OK" : "Capturar");
  setOperationStep("#step-inspection", inspection ? "ready" : "pending", inspection ? "OK reciente" : "Checklist");
  setOperationStep(
    "#step-advance",
    ["NO_LIBERAR", "FALTA_ZONA_SUPERIOR", "MOLDE_INCOMPLETO"].includes(status) ? "blocked" : canAdvance && inspection ? "ready" : "pending",
    ["NO_LIBERAR", "FALTA_ZONA_SUPERIOR", "MOLDE_INCOMPLETO"].includes(status) ? "Bloqueado" : canAdvance && inspection ? "Listo" : "Esperando"
  );
  setOperationStep("#step-condition", condition ? "ready" : "pending", condition ? condition.resultado_fisico : "Registrar");

  const issues = dataQualityIssues();
  const panel = $("#data-quality-panel");
  renderDataQualityPanel(panel, issues);
  renderDataQualityPanel($("#report-data-quality-panel"), issues);
  updateAdvanceActionLabel();
}

function renderOperatorDataChecklist() {
  const target = $("#operator-data-check-list");
  const count = $("#operator-data-check-count");
  if (!target) return;
  const issues = dataQualityIssues();
  const okItems = [];
  if (activeColado()) okItems.push("Colado activo");
  if ((state.moldState?.zonas_activas || []).length) okItems.push(`${state.moldState.zonas_activas.length} zonas registradas`);
  if (latestTemperatureReading() || state.moldState?.zona_en_liberacion?.temperatura_actual_c != null) okItems.push("Temperatura disponible");
  if (latestInspectionOk()) okItems.push("Inspeccion reciente");
  const items = [
    ...issues.map((issue) => ({ ...issue, ok: false })),
    ...okItems.map((text) => ({ level: "ok", text, ok: true })),
  ];
  target.innerHTML = items.length
    ? items.slice(0, 8).map((item) => `<span class="${escapeHtml(item.level)}">${escapeHtml(item.ok ? `OK: ${item.text}` : item.text)}</span>`).join("")
    : `<span>OK: datos suficientes para decidir con trazabilidad.</span>`;
  if (count) {
    const critical = issues.filter((item) => item.level === "critical").length;
    const warnings = issues.filter((item) => item.level === "warn").length;
    count.textContent = critical ? `${critical} critico(s)` : warnings ? `${warnings} aviso(s)` : "Completo";
  }
}

function operatorLogEntries() {
  const entries = [];
  for (const reading of (state.latestPrediction?.lecturas || []).slice(-8)) {
    entries.push({
      type: "reading",
      time: reading.fecha_hora,
      title: "Lectura temperatura",
      text: `Concreto ${format(reading.temperatura_concreto_c, 1)} C; ambiente ${format(reading.temperatura_ambiente_c, 1)} C; HR ${format(reading.humedad_relativa_pct, 1)}%.`,
    });
  }
  for (const advance of (state.moldState?.avances || []).slice(-8)) {
    entries.push({
      type: "advance",
      time: advance.fecha_hora,
      title: `Avance ${format(advance.avance_cm, 1)} cm`,
      text: `Acumulado ${format(advance.avance_acumulado_cm, 1)} cm; velocidad ${format(advance.velocidad_real_cm_h, 1)} cm/h.`,
    });
  }
  for (const decision of (state.scadaState?.decisiones_recientes || []).slice(0, 8)) {
    const field = decision.decision_operador === "LIBERAR_POR_CRITERIO_CAMPO";
    entries.push({
      type: field ? "field" : "decision",
      time: decision.fecha_hora,
      title: field ? "Lista por criterio de campo" : `Decision ${decision.decision_operador || "--"}`,
      text: `${decision.recomendacion_sistema || "--"} -> ${decision.decision_operador || "--"}${decision.supervisor ? `; supervisor ${decision.supervisor}` : ""}.`,
    });
  }
  for (const event of (state.latestPrediction?.eventos || []).slice(-6)) {
    entries.push({
      type: "event",
      time: event.fecha_hora,
      title: `Evento ${event.decision_tomada || event.resultado_fisico || "--"}`,
      text: eventLogText(event),
    });
  }
  for (const alarm of (state.scadaState?.alarmas_activas || []).slice(0, 6)) {
    entries.push({
      type: "alarm",
      time: alarm.fecha_hora_inicio,
      title: `Alarma ${alarm.severidad || "--"}`,
      text: alarm.mensaje || alarm.tipo || "Alarma operativa",
    });
  }
  return entries
    .filter((entry) => entry.time)
    .sort((a, b) => String(b.time || "").localeCompare(String(a.time || "")))
    .slice(0, 10);
}

function eventLogText(event) {
  const observation = compactHistoricalObservation(event.observacion);
  const result = event.resultado_fisico && event.resultado_fisico !== "registro_escrito"
    ? event.resultado_fisico
    : "";
  return [result, observation].filter(Boolean).join("; ") || "Registro de bitacora historica.";
}

function compactHistoricalObservation(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const importedPrefix = "Importado de bitacora escrita.";
  const cleaned = text.startsWith(importedPrefix) ? text.slice(importedPrefix.length).trim() : text;
  return cleaned.replace(/\s*Hora original:.*$/i, "").replace(/\s*Fuente:.*$/i, "").trim();
}

function renderOperatorLog() {
  const target = $("#operator-log-list");
  if (!target) return;
  const entries = operatorLogEntries();
  target.innerHTML = entries.length
    ? entries
        .map(
          (entry) => `<div class="operator-log-item ${escapeHtml(entry.type)}">
            <strong>${escapeHtml(entry.title)}</strong>
            <span>${escapeHtml(formatZoneTime(entry.time))}</span>
            <small>${escapeHtml(entry.text)}</small>
          </div>`
        )
        .join("")
    : `<div class="operator-log-empty">Sin actividad registrada.</div>`;
}

function updateInspectionSignal() {
  const el = $("#field-command-inspection");
  if (!el) return;
  const inspection = latestInspectionOk();
  if (inspection) {
    const ageMin = Math.round(Math.abs(evaluationDate() - new Date(inspection.fecha_hora)) / 60000);
    el.textContent = `OK ${ageMin} min`;
    el.className = "inspection-ok";
    const inline = $("#inspection-inline");
    if (inline) inline.textContent = `OK ${ageMin} min`;
  } else {
    el.textContent = "Pendiente";
    el.className = "inspection-pending";
    const inline = $("#inspection-inline");
    if (inline) inline.textContent = "Pendiente";
  }
  renderOperationalGuidance();
}

function moldStateUrl(options = {}) {
  const params = new URLSearchParams({ colado_id: state.activeColadoId });
  const useEvaluationTime = options.useEvaluationTime !== false;
  if (useEvaluationTime && state.evaluationTime) params.set("as_of", state.evaluationTime);
  return `/api/molde/estado?${params.toString()}`;
}

function scadaStateUrl(options = {}) {
  const params = new URLSearchParams({ colado_id: state.activeColadoId });
  const useEvaluationTime = options.useEvaluationTime !== false;
  if (useEvaluationTime && state.evaluationTime) params.set("as_of", state.evaluationTime);
  return `/api/scada/estado?${params.toString()}`;
}

function trendsUrl(options = {}) {
  const params = new URLSearchParams({ colado_id: state.activeColadoId });
  const zoneId = options.zoneId ?? $("#trend-zone-select")?.value ?? "";
  const range = options.range || $("#trend-range-select")?.value || "4h";
  if (/^\d+$/.test(String(zoneId || ""))) params.set("zona_id", zoneId);
  params.set("rango", range);
  if (options.asOf) params.set("as_of", options.asOf);
  else if (state.evaluationTime && options.useEvaluationTime !== false) params.set("as_of", state.evaluationTime);
  return `/api/tendencias?${params.toString()}`;
}

function setEvaluationTime(value) {
  state.evaluationTime = value || "";
  const input = $("#evaluation-time");
  if (input) input.value = state.evaluationTime;
  if (state.evaluationTime) {
    localStorage.setItem("evaluationTime", state.evaluationTime);
  } else {
    localStorage.removeItem("evaluationTime");
  }
  updateEvaluationHint();
}

function addEvaluationMinutes(minutes) {
  const baseValue = state.evaluationTime || $("#evaluation-time")?.value || formatDatetimeLocal(new Date());
  const base = new Date(baseValue);
  if (Number.isNaN(base.getTime())) return;
  base.setMinutes(base.getMinutes() + minutes);
  setEvaluationTime(formatDatetimeLocal(base));
}

function normalizeActiveColado() {
  if (!state.activeColadoId) return;
  const exists = (state.bootstrap.colados || []).some((colado) => String(colado.id) === String(state.activeColadoId));
  if (!exists) {
    localStorage.removeItem(`prediction:${state.activeColadoId}`);
    localStorage.removeItem("activeColadoId");
    state.activeColadoId = "";
    state.latestPrediction = null;
    state.moldState = null;
  }
}

function renderSelectors() {
  const mezclas = state.bootstrap.mezclas || [];
  const colados = state.bootstrap.colados || [];
  $("#mezcla-select").innerHTML = mezclas
    .map((m) => `<option value="${m.id}">${escapeHtml(m.nombre)}</option>`)
    .join("");
  renderCurveOptions();
  $("#colado-select").innerHTML =
    `<option value="">Seleccionar</option>` +
    colados
      .map((c) => {
        const baseTime = c.hora_colocacion_en_molde || c.fecha_hora_inicio || "";
        const label = `#${c.id} ${c.silo_id} - ${c.mezcla_nombre || ""}${
          baseTime ? " - " + baseTime.replace("T", " ") : ""
        }`;
        return `<option value="${c.id}" ${String(c.id) === String(state.activeColadoId) ? "selected" : ""}>${escapeHtml(label)}</option>`;
      })
      .join("");
  populateColadoForm();
  updateColadoActionState();
  updateLinks();
  updateTopbarContext();
}

function renderCurveOptions() {
  const mezclaId = Number($("#mezcla-select")?.value || 0);
  const curvas = (state.bootstrap.curvas || []).filter((curve) => !mezclaId || Number(curve.mezcla_id) === mezclaId);
  $("#curva-select").innerHTML =
    `<option value="">Sin curva</option>` +
    curvas.map((c) => `<option value="${c.id}">${escapeHtml(c.nombre_curva)}</option>`).join("");
}

const {
  refreshDiagnostics,
  renderDiagnostics,
  renderProjectForm,
} = window.SlipformOperationalView;

function renderOperationalData() {
  window.SlipformOperationalView.renderOperationalData(activeColado);
  renderTruckLoadsTable();
  renderReportPhotos();
  updateTruckZoneFormDefaults();
  updateStartOffsetSummary();
}

function renderReportPhotos() {
  const list = $("#report-photos-list");
  const count = $("#report-photo-count");
  if (!list && !count) return;
  const rows = state.operationalData?.fotografias || [];
  if (count) count.textContent = `${rows.length} ${rows.length === 1 ? "imagen" : "imagenes"}`;
  if (!list) return;
  list.innerHTML = rows.length
    ? rows
        .map(
          (photo) => `<figure class="photo-card report-photo-card">
            ${
              photo.imagen_data_url
                ? `<img src="${escapeHtml(photo.imagen_data_url)}" alt="${escapeHtml(photo.descripcion || "Imagen de reporte")}" />`
                : `<div class="photo-empty">Sin imagen</div>`
            }
            <figcaption>
              <strong>${escapeHtml(formatZoneTime(photo.fecha_hora))}</strong>
              <span>${escapeHtml(photo.zona_numero ? "Zona " + photo.zona_numero : "Reporte")}${
                photo.elevacion_cm ? ` - ${format(photo.elevacion_cm, 1)} cm` : ""
              }</span>
              <span>${escapeHtml(photo.descripcion || "")}</span>
            </figcaption>
          </figure>`
        )
        .join("")
    : `<div class="photo-empty">Sin imagenes cargadas para el reporte.</div>`;
}

function renderHomeSummary() {
  window.SlipformOperationalView.renderHomeSummary(activeColado);
}

function updateTopbarContext() {
  const colado = activeColado();
  $("#active-colado-pill").textContent = colado
    ? `${colado.es_demo ? "DEMO " : ""}Colado #${colado.id} - ${colado.silo_id}${isColadoClosed(colado) ? " - CERRADO" : ""}`
    : "Sin colado";
  $("#operator-pill").textContent = colado?.operador ? `Operador: ${colado.operador}` : "Sin operador";
  const fieldColado = $("#field-command-colado");
  if (fieldColado) fieldColado.textContent = colado ? `#${colado.id} ${colado.silo_id}` : "Sin colado";
  updateCaptureReadiness();
}

function populateColadoForm() {
  const form = $("#colado-form");
  const colado = activeColado();
  if (!colado) {
    form.reset();
    renderCurveOptions();
    return;
  }
  form.elements.silo_id.value = colado.silo_id || "";
  form.elements.mezcla_id.value = colado.mezcla_id || "";
  renderCurveOptions();
  form.elements.curva_id.value = colado.curva_id || "";
  form.elements.operador.value = colado.operador || "";
  form.elements.estado.value = colado.estado || "ACTIVO";
  form.elements.fecha_cierre.value = toDatetimeLocalValue(colado.fecha_cierre);
  form.elements.es_demo.checked = Boolean(Number(colado.es_demo || 0));
  form.elements.observaciones.value = colado.observaciones || "";
  applyClosedColadoUi();
}

function updateColadoActionState() {
  const hasActive = Boolean(state.activeColadoId && activeColado());
  $("#update-colado-btn").disabled = !hasActive;
  $("#delete-colado-btn").disabled = !hasActive;
  applyClosedColadoUi();
}

function isColadoClosed(colado = activeColado()) {
  return String(colado?.estado || "").toUpperCase() === "CERRADO";
}

function coladoClosureText(colado = activeColado()) {
  return colado?.fecha_cierre ? `Cerrado: ${formatZoneTime(colado.fecha_cierre)}` : "Cerrado sin fecha registrada";
}

function applyClosedColadoUi() {
  const closed = isColadoClosed();
  const selectors = [
    "#advance-recipe-form",
    "#start-offset-form",
    "#truck-zone-form",
    "#zone-generator-form",
    "#reading-form",
    "#advance-form",
    "#slip-schedule-form",
  ];
  selectors.forEach((selector) => {
    const form = $(selector);
    if (!form) return;
    [...form.elements].forEach((field) => {
      if (field.closest("#colado-form")) return;
      field.disabled = closed;
    });
    form.classList.toggle("closed-disabled", closed);
  });
}

async function refreshPrediction() {
  if (!state.activeColadoId) {
    renderPrediction(null);
    return;
  }
  try {
    const result = await api(`/api/prediccion?colado_id=${state.activeColadoId}`);
    state.latestPrediction = result;
    localStorage.setItem(`prediction:${state.activeColadoId}`, JSON.stringify(result));
    setConnection("En linea", true);
    renderPrediction(result);
  } catch (error) {
    if (error.status === 404) {
      clearActiveColado();
      return;
    }
    setConnection("Sin conexion", false);
    renderPrediction(localPrediction());
  }
}

async function refreshMoldState() {
  if (!state.activeColadoId) {
    renderMoldState(null);
    await refreshDataQuality();
    return;
  }
  try {
    state.moldState = await api(moldStateUrl());
    renderMoldState(state.moldState);
    await refreshDataQuality();
  } catch (error) {
    if (error.status === 400 || error.status === 404) {
      clearActiveColado();
      return;
    }
    renderMoldState(null);
    await refreshDataQuality();
  }
}

async function refreshScadaState() {
  state.scadaState = null;
}

async function refreshTrends() {
  if (!state.activeColadoId) {
    renderOperatorLiveTrend(null);
    return;
  }
  try {
    state.trends = await api(trendsUrl());
    renderOperatorLiveTrend(state.operatorTrends || state.trends);
  } catch (error) {
    renderOperatorLiveTrend(null);
  }
}

async function refreshSlipSchedule() {
  if (!state.activeColadoId) {
    state.schedule = null;
    renderSlipSchedule(null);
    renderOperatorSchedule(null);
    return;
  }
  try {
    state.schedule = await api(`/api/programa-deslizado?colado_id=${encodeURIComponent(state.activeColadoId)}`);
    renderSlipSchedule(state.schedule);
    renderOperatorSchedule(state.schedule);
  } catch (error) {
    state.schedule = null;
    renderSlipSchedule(null);
    renderOperatorSchedule(null);
  }
}

async function refreshDataQuality() {
  if (!state.activeColadoId) {
    state.dataQuality = null;
    renderOperationalGuidance();
    return;
  }
  try {
    const result = await api(`/api/calidad-datos?colado_id=${encodeURIComponent(state.activeColadoId)}`);
    state.dataQuality = result.calidad_datos || null;
  } catch (error) {
    state.dataQuality = null;
  }
  renderOperationalGuidance();
}

async function refreshOperatorTrendsSilently() {
  if (!state.activeColadoId) {
    state.operatorTrends = null;
    renderOperatorLiveTrend(null);
    return;
  }
  const zoneId = state.moldState?.zona_en_liberacion?.id || "";
  try {
    state.operatorTrends = await api(trendsUrl({ zoneId, range: "todo", useEvaluationTime: false }));
    renderOperatorLiveTrend(state.operatorTrends);
  } catch (error) {
    renderOperatorLiveTrend(state.operatorTrends || state.trends || null);
  }
}

async function refreshOperationalData() {
  if (!state.activeColadoId) {
    state.operationalData = { turnos: [], fotografias: [], desplomes: [], ajustes: [], sensores: [], descargas: [] };
    renderOperationalData();
    await refreshDataQuality();
    return;
  }
  try {
    const params = `colado_id=${encodeURIComponent(state.activeColadoId)}`;
    const descargas = await api(`/api/descargas?${params}`);
    const photos = await api(`/api/fotografias?${params}`);
    state.operationalData = {
      turnos: [],
      fotografias: photos.fotografias || [],
      desplomes: [],
      ajustes: [],
      sensores: [],
      descargas: descargas.descargas || [],
    };
    renderOperationalData();
    await refreshDataQuality();
  } catch (error) {
    renderOperationalData();
    await refreshDataQuality();
  }
}

function clearActiveColado() {
  if (state.activeColadoId) {
    localStorage.removeItem(`prediction:${state.activeColadoId}`);
    delete state.localReadings[String(state.activeColadoId)];
    localStorage.setItem("localReadings", JSON.stringify(state.localReadings));
  }
  localStorage.removeItem("activeColadoId");
  state.activeColadoId = "";
  state.latestPrediction = null;
  state.moldState = null;
  state.scadaState = null;
  state.trends = null;
  state.schedule = null;
  state.dataQuality = null;
  setConnection("En linea", true);
  renderSelectors();
  renderPrediction(null);
  renderMoldState(null);
  renderOperatorLiveTrend(null);
  renderSlipSchedule(null);
  renderOperatorSchedule(null);
  refreshOperationalData();
}

function localPrediction() {
  const params = state.bootstrap.params || defaultParams();
  const readings = state.localReadings[state.activeColadoId] || [];
  if (!readings.length) return JSON.parse(localStorage.getItem(`prediction:${state.activeColadoId}`) || "null");
  let maturity = 0;
  let previous = null;
  const sorted = readings
    .map((r) => ({
      minuto: Number(r.minuto_transcurrido),
      temp: Number(r.temperatura_concreto_c),
      ambient: r.temperatura_ambiente_c,
      humidity: r.humedad_relativa_pct,
      origen: r.origen,
    }))
    .filter((r) => Number.isFinite(r.minuto) && Number.isFinite(r.temp))
    .sort((a, b) => a.minuto - b.minuto);
  const maturityPoints = [];
  for (const reading of sorted) {
    if (!previous) {
      maturity += Math.max(0, reading.minuto / 60) * arrhenius(reading.temp, params);
    } else {
      const dt = (reading.minuto - previous.minuto) / 60;
      if (dt > 0) maturity += dt * arrhenius((reading.temp + previous.temp) / 2, params);
    }
    maturityPoints.push({
      minuto: reading.minuto,
      temperatura_concreto_c: reading.temp,
      madurez_arrhenius_h_eq: maturity,
    });
    previous = reading;
  }
  const latest = sorted[sorted.length - 1];
  const advance = maturity / params.target_maturity_h_eq;
  return {
    estado: stateForAdvance(advance),
    avance: advance,
    madurez_acumulada_h_eq: maturity,
    minutos_estimados_restantes: Math.max(
      0,
      ((params.target_maturity_h_eq - maturity) / arrhenius(latest.temp, params)) * 60
    ),
    temperatura_actual_concreto_c: latest.temp,
    alertas: ["Calculo local sin sincronizar."],
    lecturas: sorted.map((r) => ({
      minuto_transcurrido: r.minuto,
      temperatura_concreto_c: r.temp,
      temperatura_ambiente_c: r.ambient,
      humedad_relativa_pct: r.humidity,
      origen: r.origen,
    })),
    eventos: [],
    puntos_madurez: maturityPoints,
  };
}

function renderPrediction(result) {
  const estado = result?.estado || "SIN_DATOS";
  const badge = $("#state-badge");
  if (badge) {
    badge.textContent = estado.replaceAll("_", " ");
    badge.className = `state ${stateClass(estado)}`;
  }
  if ($("#maturity")) $("#maturity").textContent = `${format(result?.madurez_acumulada_h_eq, 2)} h_eq`;
  if ($("#advance")) $("#advance").textContent = `${format((result?.avance || 0) * 100, 1)}%`;
  if ($("#remaining")) {
    $("#remaining").textContent =
      result?.minutos_estimados_restantes == null ? "-- min" : `${format(result.minutos_estimados_restantes, 0)} min`;
  }
  if ($("#latest-temp")) {
    $("#latest-temp").textContent =
      result?.temperatura_actual_concreto_c == null ? "-- C" : `${format(result.temperatura_actual_concreto_c, 1)} C`;
  }
  if ($("#alerts")) $("#alerts").innerHTML = (result?.alertas || []).map((a) => `<div>${escapeHtml(a)}</div>`).join("");
  renderReadings(result?.lecturas || []);
  renderHomeSummary();
  renderOperationalGuidance();
}

function renderMoldState(result) {
  updateEvaluationHint(result?.hora_evaluacion || "");
  setFieldCommandState(result);
  renderTruckLoadsTable();
  renderZoneSelectors(result?.zonas_activas || []);
  renderAdvanceRecipe(result?.receta_avance || null);
  renderHomeSummary();
  updateCaptureReadiness();
  updateZoneGeneratorSummary();
  renderOperationalGuidance();
  renderOperatorTab(result);
}

function updateDecisionMaturityTone(advanceMaturity) {
  const item = document.querySelector(".decision-kpis .kpi-maturity");
  if (!item) return;
  item.classList.remove("maturity-critical", "maturity-warning", "maturity-ok", "maturity-over");
  const pct = Number(advanceMaturity || 0) * 100;
  if (!Number.isFinite(pct) || pct <= 0) return;
  if (pct < 70) item.classList.add("maturity-critical");
  else if (pct < 90) item.classList.add("maturity-warning");
  else if (pct <= 105) item.classList.add("maturity-ok");
  else item.classList.add("maturity-over");
}

function activeAdvanceRecipe() {
  return state.moldState?.receta_avance || {
    avance_objetivo_cm: DEFAULT_ADVANCE_CM,
    intervalo_objetivo_min: DEFAULT_ADVANCE_INTERVAL_MIN,
    velocidad_objetivo_cm_h: DEFAULT_ADVANCE_SPEED_CM_H,
    tolerancia_velocidad_min_cm_h: Math.max(0, DEFAULT_ADVANCE_SPEED_CM_H - 5),
    tolerancia_velocidad_max_cm_h: DEFAULT_ADVANCE_SPEED_CM_H + 5,
  };
}

function calculateRecipeSpeeds(advanceCm, intervalMin) {
  const advance = Number(advanceCm);
  const interval = Number(intervalMin);
  if (!Number.isFinite(advance) || !Number.isFinite(interval) || advance <= 0 || interval <= 0) {
    return null;
  }
  const speed = (advance / interval) * 60;
  return {
    velocidad_objetivo_cm_h: speed,
    tolerancia_velocidad_min_cm_h: Math.max(0, speed - 5),
    tolerancia_velocidad_max_cm_h: speed + 5,
  };
}

function syncAdvanceRecipeToleranceFields(recipe) {
  const form = $("#advance-recipe-form");
  if (!form || !recipe) return;
  if (Number.isFinite(Number(recipe.tolerancia_velocidad_min_cm_h))) {
    form.elements.tolerancia_velocidad_min_cm_h.value = format(recipe.tolerancia_velocidad_min_cm_h, 1);
  }
  if (Number.isFinite(Number(recipe.tolerancia_velocidad_max_cm_h))) {
    form.elements.tolerancia_velocidad_max_cm_h.value = format(recipe.tolerancia_velocidad_max_cm_h, 1);
  }
}

function recipeFromAdvanceForm() {
  const form = $("#advance-recipe-form");
  if (!form) return activeAdvanceRecipe();
  const active = activeAdvanceRecipe();
  const finalAdvance = Number(form.elements.avance_objetivo_cm.value || active.avance_objetivo_cm || DEFAULT_ADVANCE_CM);
  const finalInterval = Number(form.elements.intervalo_objetivo_min.value || active.intervalo_objetivo_min || DEFAULT_ADVANCE_INTERVAL_MIN);
  const speeds = calculateRecipeSpeeds(finalAdvance, finalInterval);
  return {
    ...active,
    avance_objetivo_cm: finalAdvance,
    intervalo_objetivo_min: finalInterval,
    velocidad_objetivo_cm_h: speeds?.velocidad_objetivo_cm_h ?? active.velocidad_objetivo_cm_h,
    tolerancia_velocidad_min_cm_h: speeds?.tolerancia_velocidad_min_cm_h ?? active.tolerancia_velocidad_min_cm_h,
    tolerancia_velocidad_max_cm_h: speeds?.tolerancia_velocidad_max_cm_h ?? active.tolerancia_velocidad_max_cm_h,
  };
}

function updateAdvanceActionLabel(recipe = activeAdvanceRecipe(), pending = false) {
  const button = $("#advance-5min-btn");
  if (!button) return;
  if (isColadoClosed()) {
    button.textContent = "Colado finalizado";
    button.title = coladoClosureText();
    button.disabled = true;
    return;
  }
  button.disabled = false;
  const advance = Number(recipe?.avance_objetivo_cm || 0);
  const interval = Number(recipe?.intervalo_objetivo_min || 0);
  const status = state.moldState?.estado_operativo || "SIN_ZONAS";
  if (status === "SIN_ZONAS") {
    button.textContent = "Registrar Olla 1";
  } else if (status === "MOLDE_INCOMPLETO") {
    button.textContent = "Registrar siguiente olla";
  } else if (status === "PREPARARSE") {
    button.textContent = Number.isFinite(advance) && advance > 0
      ? `Prepararse / deslizado +${format(advance, 1)} cm`
      : "Prepararse / deslizado";
  } else if (status === "NO_LIBERAR" || status === "FALTA_ZONA_SUPERIOR") {
    button.textContent = "No deslizar / requiere supervisor";
  } else if (status === "RIESGO_AGARROTAMIENTO") {
    button.textContent = Number.isFinite(advance) && advance > 0
      ? `Deslizar con vigilancia +${format(advance, 1)} cm`
      : "Deslizar con vigilancia";
  } else {
    button.textContent = Number.isFinite(advance) && advance > 0
      ? `Registrar deslizado +${format(advance, 1)} cm`
      : "Registrar deslizado";
  }
  button.title = Number.isFinite(interval) && interval > 0
    ? `${pending ? "Vista previa sin guardar. " : ""}Receta: ${format(advance, 1)} cm cada ${format(interval, 1)} min.`
    : "";
}

function updateAdvanceRecipeSummary(recipe, pending = false) {
  const summary = $("#advance-recipe-summary");
  if (!summary || !recipe) return;
  summary.textContent = `${pending ? "Vista previa: " : "Activa: "}${format(recipe.avance_objetivo_cm, 1)} cm cada ${format(
    recipe.intervalo_objetivo_min,
    1
  )} min = ${format(recipe.velocidad_objetivo_cm_h, 1)} cm/h. Tolerancia ${format(
    recipe.tolerancia_velocidad_min_cm_h,
    1
  )}-${format(recipe.tolerancia_velocidad_max_cm_h, 1)} cm/h.`;
}

function renderAdvanceRecipe(recipe) {
  const form = $("#advance-recipe-form");
  if (!form || !recipe) return;
  form.elements.avance_objetivo_cm.value = format(recipe.avance_objetivo_cm, 1);
  form.elements.intervalo_objetivo_min.value = format(recipe.intervalo_objetivo_min, 1);
  form.elements.tolerancia_velocidad_min_cm_h.value = format(recipe.tolerancia_velocidad_min_cm_h, 1);
  form.elements.tolerancia_velocidad_max_cm_h.value = format(recipe.tolerancia_velocidad_max_cm_h, 1);
  form.elements.motivo.value = recipe.motivo && !String(recipe.motivo).startsWith("Default") ? recipe.motivo : "";
  form.elements.operador.value = recipe.operador || activeColado()?.operador || "";
  form.elements.supervisor.value = recipe.supervisor || "";
  updateAdvanceActionLabel(recipe);
  updateAdvanceRecipeSummary(recipe);
  renderAdvanceRecipeSuggestion(state.moldState);
  renderOperatorTab(state.moldState);
}

function latestMoldAdvance() {
  const advances = state.moldState?.avances || [];
  return advances
    .slice()
    .filter((advance) => advance.fecha_hora)
    .sort((a, b) => new Date(b.fecha_hora) - new Date(a.fecha_hora))[0] || null;
}

function operatorActionForStatus(status) {
  if (isColadoClosed()) return { action: "closed", label: "Colado finalizado", display: "FINALIZADO" };
  if (!activeColado() || status === "SIN_ZONAS") return { action: "capture", label: "Ir a Captura", display: "SIN ZONAS" };
  if (status === "MOLDE_INCOMPLETO") return { action: "register-truck", label: "Registrar siguiente olla", display: "ESPERAR" };
  if (status === "NO_LIBERAR" || status === "FALTA_ZONA_SUPERIOR") return { action: "wait", label: "Esperar", display: "ESPERAR" };
  if (status === "PREPARARSE") return { action: "review", label: "Revisar", display: "REVISAR" };
  if (status === "RIESGO_AGARROTAMIENTO") return { action: "slide-risk", label: "Deslizar con vigilancia", display: "RIESGO" };
  if (status === "CONTINUAR") return { action: "slide", label: "Deslizar", display: "DESLIZAR" };
  return { action: "review", label: "Revisar", display: status.replaceAll("_", " ") };
}

function canMarkReadyByFieldCriteria(result = state.moldState) {
  if (isColadoClosed()) return false;
  if (!activeColado() || !result) return false;
  const status = result.estado_operativo || "SIN_ZONAS";
  if (["MOLDE_INCOMPLETO", "FALTA_ZONA_SUPERIOR", "SIN_ZONA_A_LIBERAR", "SIN_ZONAS"].includes(status)) return false;
  const zone = result.zona_en_liberacion || null;
  if (!zone?.id || zone.madurez_override_activa) return false;
  const params = state.bootstrap.params || defaultParams();
  const threshold = Number(params.slide_threshold || 0.9);
  const calculated = Number(zone.avance_madurez_calculada ?? zone.avance_madurez ?? 0);
  return Number.isFinite(calculated) && calculated >= 0 && calculated < threshold;
}

function renderOperatorTab(result) {
  const statusEl = $("#operator-status");
  if (!statusEl) return;
  const colado = activeColado();
  const closed = isColadoClosed(colado);
  const status = closed ? "CERRADO" : result?.estado_operativo || "SIN_ZONAS";
  const zone = result?.zona_en_liberacion || null;
  const recipe = activeAdvanceRecipe();
  const action = operatorActionForStatus(status);
  const button = $("#operator-action-btn");
  statusEl.textContent = action.display;
  statusEl.className = moldStateClass(status);
  updateOperatorCommandBar({
    status,
    statusText: action.display,
    zoneText: closed ? coladoClosureText(colado) : zone ? `Zona ${zone.zona_numero}` : "--",
  });
  $("#operator-message").textContent = operatorMessage(result, action.action);
  $("#operator-zone").textContent = closed ? "Colado cerrado" : zone ? `Zona ${zone.zona_numero}` : "--";
  const loadInfo = $("#operator-zone-load");
  if (loadInfo) {
    loadInfo.textContent = closed
      ? coladoClosureText(colado)
      : zone
      ? zone.es_zona_heredada
        ? "Existente previo | Sin olla de este colado"
        : `Olla ${zone.numero_olla || zone.zona_numero || "--"} | Salida planta: ${formatZoneTime(zone.hora_salida_planta || zone.hora_referencia_madurez)}`
      : "Olla: -- | Salida planta: --";
  }
  $("#operator-maturity").textContent = zone ? `${format(zone.avance_madurez * 100, 1)}%` : "--%";
  const fieldReleaseBadge = $("#operator-field-release-badge");
  if (fieldReleaseBadge) {
    const hasFieldRelease = Boolean(zone?.madurez_override_activa);
    const calculated = zone?.avance_madurez_calculada == null ? null : Number(zone.avance_madurez_calculada) * 100;
    const effective = zone?.avance_madurez_efectiva == null ? Number(zone?.avance_madurez || 0) * 100 : Number(zone.avance_madurez_efectiva) * 100;
    fieldReleaseBadge.hidden = !hasFieldRelease;
    fieldReleaseBadge.textContent = hasFieldRelease
      ? `Lista por criterio de campo: calculada ${format(calculated, 1)}% / operativa ${format(effective, 1)}%.`
      : "";
  }
  $("#operator-temp").textContent = zone?.temperatura_actual_c == null ? "-- C" : `${format(zone.temperatura_actual_c, 1)} C`;
  $("#operator-advance").textContent = `${format(recipe.avance_objetivo_cm, 1)} cm`;
  $("#operator-recipe").textContent = `Receta: ${format(recipe.avance_objetivo_cm, 1)} cm cada ${format(recipe.intervalo_objetivo_min, 1)} min`;
  const zoneTempButton = $("#operator-zone-temp-btn");
  if (zoneTempButton) {
    const canCaptureZoneTemp = Boolean(!closed && zone?.id && !zone.pendiente_olla);
    zoneTempButton.hidden = !canCaptureZoneTemp;
    zoneTempButton.disabled = !canCaptureZoneTemp;
    zoneTempButton.textContent = zone ? `Temperatura Zona ${zone.zona_numero}` : "Capturar temperatura";
    zoneTempButton.dataset.zoneId = canCaptureZoneTemp ? String(zone.id) : "";
  }
  renderOperatorMoldProgress(result);
  renderOperatorSpeedAdvice(result);
  renderOperatorSchedule(state.schedule);
  renderOperatorLiveTrend(state.operatorTrends || state.trends || null);
  renderOperatorDataChecklist();
  renderOperatorLog();
  if (button) {
    button.textContent = action.label;
    button.dataset.baseAction = action.action;
    button.dataset.action = action.action;
    button.classList.toggle("blocked", action.action === "wait");
    button.disabled = closed;
    button.classList.toggle("closed", closed);
    button.classList.toggle("risk", action.action === "slide-risk");
  }
  const authorizeButton = $("#operator-authorize-btn");
  if (authorizeButton) {
    const canRequestAuthorization = canMarkReadyByFieldCriteria(result);
    authorizeButton.hidden = !canRequestAuthorization;
    authorizeButton.textContent = canRequestAuthorization
      ? `Marcar lista por inspeccion - Zona ${zone.zona_numero}`
      : "Marcar lista por inspeccion";
  }
  const criticalAlarm = (state.scadaState?.alarmas_activas || []).find((alarm) =>
    ["CRITICA", "ALTA"].includes(String(alarm.severidad || "").toUpperCase())
  );
  const warning = $("#operator-warning");
  if (warning) {
    warning.textContent = criticalAlarm ? criticalAlarm.mensaje || criticalAlarm.tipo : "Sin alarmas criticas.";
    warning.classList.toggle("active", Boolean(criticalAlarm));
  }
  updateOperatorTimer();
}

function updateOperatorCommandBar({ status, statusText, zoneText, advanceText, nextText } = {}) {
  const bar = $(".operator-command-bar");
  if (!bar) return;
  if (status) bar.className = `operator-command-bar ${moldStateClass(status)}`;
  const stateTarget = $("#operator-command-state");
  const zoneTarget = $("#operator-command-zone");
  const advanceTarget = $("#operator-command-advance");
  const nextTarget = $("#operator-command-next");
  if (stateTarget && statusText) stateTarget.textContent = statusText;
  if (zoneTarget && zoneText) zoneTarget.textContent = zoneText;
  if (advanceTarget && advanceText) advanceTarget.textContent = advanceText;
  if (nextTarget && nextText) nextTarget.textContent = nextText;
}

function renderOperatorSpeedAdvice(result) {
  const target = $("#operator-speed-advice");
  if (!target) return;
  const prediction = result?.prediccion_deslizamiento || {};
  const suggestion = prediction.receta_sugerida || null;
  const speed = prediction.velocidad_recomendada_cm_h;
  const action = prediction.accion_recomendada || prediction.estado_velocidad || "sin_datos";
  const stateClass = `speed-${String(prediction.estado_velocidad || action || "sin_datos").replaceAll("_", "-")}`;
  target.className = `operator-speed-advice-card ${stateClass}`;
  $("#operator-speed-recommendation").textContent =
    speed == null ? "-- cm/h" : `${format(speed, 1)} cm/h`;
  $("#operator-speed-action").textContent = speedActionLabel(action);
  $("#operator-speed-reason").textContent =
    prediction.motivo_recomendacion || "Registra zonas y temperatura para calcular recomendacion.";
  const suggested = $("#operator-speed-suggested");
  if (suggested) {
    suggested.textContent = suggestion
      ? `Sugerencia: ${recipeSuggestionText(suggestion)}. Receta activa: ${format(activeAdvanceRecipe().avance_objetivo_cm, 1)} cm cada ${format(activeAdvanceRecipe().intervalo_objetivo_min, 1)} min.`
      : `Receta activa: ${format(activeAdvanceRecipe().avance_objetivo_cm, 1)} cm cada ${format(activeAdvanceRecipe().intervalo_objetivo_min, 1)} min.`;
  }
  const applyButton = $("#operator-apply-speed-recipe-btn");
  if (applyButton) {
    applyButton.hidden = !suggestion;
    applyButton.disabled = !suggestion;
    applyButton.textContent = suggestion?.requiere_supervisor ? "Aplicar con supervisor" : "Aplicar sugerencia";
  }
  renderAdvanceRecipeSuggestion(result);
}

function speedActionLabel(value) {
  const action = String(value || "").toLowerCase();
  if (action === "mantener") return "Mantener receta";
  if (action === "reducir") return "Reducir velocidad";
  if (action === "pausar") return "Pausar";
  if (action === "acelerar") return "Acelerar";
  if (action === "acelerar_con_supervision") return "Acelerar con supervisor";
  if (action === "acelerar_con_riesgo") return "Acelerar con riesgo";
  if (action === "bloquear") return "Bloqueado";
  return "Sin datos";
}

function renderAdvanceRecipeSuggestion(result) {
  const box = $("#advance-recipe-suggestion");
  if (!box) return;
  const suggestion = result?.prediccion_deslizamiento?.receta_sugerida || null;
  box.hidden = !suggestion;
  if (!suggestion) return;
  const active = activeAdvanceRecipe();
  $("#advance-recipe-suggestion-text").textContent = recipeSuggestionText(suggestion);
  $("#advance-recipe-suggestion-compare").textContent =
    `Receta activa: ${format(active.avance_objetivo_cm, 1)} cm cada ${format(active.intervalo_objetivo_min, 1)} min = ${format(active.velocidad_objetivo_cm_h, 1)} cm/h.`;
}

function recipeSuggestionText(suggestion) {
  if (!suggestion) return "--";
  return `${format(suggestion.avance_objetivo_cm, 1)} cm cada ${format(suggestion.intervalo_objetivo_min, 1)} min = ${format(
    suggestion.velocidad_objetivo_cm_h,
    1
  )} cm/h`;
}

function renderSlipSchedule(result) {
  const form = $("#slip-schedule-form");
  const scenarioEl = $("#program-scenario");
  if (!form || !scenarioEl) return;
  const ensayo = result?.ensayo || null;
  const programa = result?.programa || null;
  const estado = result?.estado_ensayo || {};
  const active = activeColado();
  if (ensayo) {
    form.elements.t_fabricacion.value = toDatetimeLocalValue(ensayo.t_fabricacion);
    form.elements.start_zone.value = ensayo.start_zone || 1;
    form.elements.layer_thickness_cm.value = format(ensayo.layer_thickness_cm || 30, 1);
    form.elements.total_layers.value = ensayo.total_layers || 7;
    form.elements.resultado_4h.value = ensayo.resultado_4h || "PENDIENTE";
    form.elements.resultado_5h.value = ensayo.resultado_5h || "PENDIENTE";
    form.elements.resultado_6h.value = ensayo.resultado_6h || "PENDIENTE";
    form.elements.operador.value = ensayo.operador || active?.operador || "";
    form.elements.supervisor.value = ensayo.supervisor || "";
    form.elements.observaciones.value = ensayo.observaciones || "";
  } else {
    form.elements.operador.value = active?.operador || "";
    if (!form.elements.t_fabricacion.value) {
      const firstZone = (state.moldState?.zonas_activas || []).find((zone) => zone.hora_salida_planta);
      form.elements.t_fabricacion.value = toDatetimeLocalValue(firstZone?.hora_salida_planta || "");
    }
  }
  const recipe = estado.receta_sugerida || programaToSuggestion(programa);
  scenarioEl.textContent = estado.escenario_activo || estado.estado || "Sin escenario";
  scenarioEl.className = `program-status-pill ${escapeHtml(estado.escenario_activo ? "ACTIVO" : estado.estado || "")}`;
  $("#program-recipe").textContent = recipe ? recipeSuggestionText(recipe) : "--";
  $("#program-message").textContent = estado.mensaje || "Registra el resultado del cilindro.";
  const apply = $("#program-apply-recipe-btn");
  if (apply) {
    apply.hidden = !recipe;
    apply.disabled = !recipe;
  }
  updateCylinderResultControls(form);
  renderSimpleSlipSchedule(result);
  renderSlipScheduleHistory(result?.historial || []);
  renderSlipScheduleLayers(result?.capas || []);
}

function programaToSuggestion(programa) {
  if (!programa) return null;
  return {
    avance_objetivo_cm: Number(programa.step_cm),
    intervalo_objetivo_min: Number(programa.step_minutes),
    velocidad_objetivo_cm_h: Number(programa.speed_cm_h),
    tolerancia_velocidad_min_cm_h: Math.max(0, Number(programa.speed_cm_h) - 5),
    tolerancia_velocidad_max_cm_h: Number(programa.speed_cm_h) + 5,
    motivo: `Receta aplicada desde programa de cilindro ${programa.escenario}.`,
  };
}

function renderSlipScheduleLayers(layers) {
  const tbody = $("#program-layers-table");
  const summary = $("#program-table-summary");
  if (!tbody) return;
  if (!layers.length) {
    tbody.innerHTML = `<tr><td colspan="9">Sin programa activo. Registra un cilindro que pase a 4h, 5h o 6h.</td></tr>`;
    if (summary) summary.textContent = "Sin programa activo.";
    return;
  }
  if (summary) {
    const registered = layers.filter((layer) => layer.hora_real_salida_planta).length;
    summary.textContent = `${registered}/${layers.length} capas con salida real registrada.`;
  }
  tbody.innerHTML = layers.map((layer) => {
    const drift = layer.desviacion_salida_min == null ? "--" : `${format(layer.desviacion_salida_min, 0)} min`;
    const status = layer.estado_programa || "PENDIENTE";
    const scenario = String(layer.escenario || "").replace("SCENARIO_", "") || "--";
    const recipe = layer.step_cm
      ? `${format(layer.step_cm, 1)} cm / ${format(layer.step_minutes, 1)} min`
      : "--";
    return `<tr>
      <td>${escapeHtml(layer.capa_numero)}</td>
      <td>Zona ${escapeHtml(layer.zona_numero)}</td>
      <td>${escapeHtml(formatZoneTime(layer.hora_programada))}<br><small>${escapeHtml(layer.offset_min || 0)} min</small></td>
      <td>${escapeHtml(formatZoneTime(layer.hora_real_salida_planta))}</td>
      <td><span class="program-status-pill ACTIVO">${escapeHtml(scenario)}</span></td>
      <td>${escapeHtml(recipe)}</td>
      <td>${escapeHtml(drift)}</td>
      <td><span class="program-status-pill ${escapeHtml(status)}">${escapeHtml(status.replaceAll("_", " "))}</span></td>
      <td><small>${escapeHtml(layer.origen_programa || "--")}</small></td>
    </tr>`;
  }).join("");
}

function renderSlipScheduleHistory(items) {
  const target = $("#program-history-list");
  if (!target) return;
  if (!items.length) {
    target.innerHTML = `<div class="empty-state">Sin revisiones registradas.</div>`;
    return;
  }
  target.innerHTML = items.slice().reverse().map((item, index) => {
    const scenario = String(item.escenario_resuelto || item.escenario_activo || item.estado || "SIN_ESCENARIO").replace("SCENARIO_", "");
    const recipe = item.receta_sugerida ? recipeSuggestionText(item.receta_sugerida) : "--";
    return `<article class="program-history-item">
      <small>Revision ${items.length - index}</small>
      <strong>Zona ${escapeHtml(item.start_zone || 1)} - ${escapeHtml(scenario)}</strong>
      <span>Salida: ${escapeHtml(formatZoneTime(item.t_fabricacion))}</span>
      <span>Receta: ${escapeHtml(recipe)}</span>
      <span>${escapeHtml(item.mensaje || item.observaciones || "")}</span>
    </article>`;
  }).join("");
}

function updateCylinderResultControls(form = $("#slip-schedule-form")) {
  if (!form) return;
  const r4 = form.elements.resultado_4h;
  const r5 = form.elements.resultado_5h;
  const r6 = form.elements.resultado_6h;
  if (!r4 || !r5 || !r6) return;
  r5.disabled = r4.value !== "FALLA";
  r6.disabled = !(r4.value === "FALLA" && r5.value === "FALLA");
  if (r4.value === "PASA") {
    r5.value = "PENDIENTE";
    r6.value = "PENDIENTE";
  }
  if (r4.value !== "FALLA") {
    r5.value = "PENDIENTE";
    r6.value = "PENDIENTE";
  } else if (r5.value !== "FALLA") {
    r6.value = "PENDIENTE";
  }
}

function renderSimpleSlipSchedule(result) {
  const zoneEl = $("#program-simple-zone");
  if (!zoneEl) return;
  const form = $("#slip-schedule-form");
  const zone = selectedCylinderEvaluationZone(result, form);
  const zoneData = simpleScheduleZoneData(result, zone);
  const latestForZone = latestScheduleRevisionForZone(result?.historial || [], zone);
  const thickness = Number(form?.elements.layer_thickness_cm?.value || result?.ensayo?.layer_thickness_cm || 30);
  const total = Number(form?.elements.total_layers?.value || result?.ensayo?.total_layers || 7);
  const canEvaluate = Boolean(zoneData.salida);
  zoneEl.textContent = `Zona ${zone}`;
  $("#program-simple-start").textContent = formatZoneTime(zoneData.salida) || "--";
  $("#program-simple-thickness").textContent = `${format(thickness, 1)} cm`;
  $("#program-simple-total").textContent = String(total || 7);
  const message = $("#program-simple-message");
  if (message) {
    const statusText = latestForZone ? simpleRevisionText(latestForZone) : "";
    message.textContent = canEvaluate
      ? statusText || `Lista para registrar resultado de cilindro de Zona ${zone}.`
      : `Registra la olla de la Zona ${zone} con salida de planta antes de evaluar cilindro.`;
    message.classList.toggle("blocked", !canEvaluate);
    message.classList.toggle("saved", Boolean(latestForZone));
  }
  const nextLoad = $("#program-next-load-summary");
  if (nextLoad) {
    const nextZone = Number(result?.siguiente_zona_programa || 0);
    nextLoad.textContent = nextZone && nextZone !== zone
      ? `Siguiente olla programada: Zona ${nextZone}`
      : "Siguiente olla programada: segun captura";
  }
  if (form) {
    form.elements.start_zone.value = zone;
    if (zoneData.salida) form.elements.t_fabricacion.value = toDatetimeLocalValue(zoneData.salida);
    if (!form.elements.layer_thickness_cm.value) form.elements.layer_thickness_cm.value = "30.0";
    if (!form.elements.total_layers.value) form.elements.total_layers.value = String(result?.ensayo?.total_layers || 7);
  }
  const r4 = latestForZone?.resultado_4h || "PENDIENTE";
  const r5 = latestForZone?.resultado_5h || "PENDIENTE";
  const finalResult = Boolean(latestForZone?.escenario_resuelto) || (r4 === "FALLA" && r5 === "FALLA" && latestForZone?.resultado_6h === "FALLA");
  setSimpleButtonState("#program-pass-4h-btn", canEvaluate && !finalResult && r4 === "PENDIENTE");
  setSimpleButtonState("#program-fail-4h-btn", canEvaluate && !finalResult && r4 === "PENDIENTE");
  setSimpleButtonState("#program-pass-5h-btn", canEvaluate && r4 === "FALLA" && r5 !== "FALLA");
  setSimpleButtonState("#program-fail-5h-btn", canEvaluate && r4 === "FALLA" && r5 !== "FALLA");
  setSimpleButtonState("#program-pass-6h-btn", canEvaluate && !finalResult && r4 === "FALLA" && r5 === "FALLA");
  setSimpleButtonState("#program-fail-6h-btn", canEvaluate && !finalResult && r4 === "FALLA" && r5 === "FALLA");
  const capture = $("#program-go-capture-btn");
  if (capture) capture.hidden = canEvaluate;
  const nextEvaluation = Number(result?.zona_evaluacion_cilindro || 0);
  const nextEvaluationButton = $("#program-next-evaluation-btn");
  if (nextEvaluationButton) {
    const showNext = Boolean(latestForZone && nextEvaluation && nextEvaluation !== zone);
    nextEvaluationButton.hidden = !showNext;
    nextEvaluationButton.disabled = state.programSimpleSaving || !showNext;
    if (showNext) nextEvaluationButton.textContent = `Evaluar Zona ${nextEvaluation}`;
  }
  const correctionButton = $("#program-correct-result-btn");
  if (correctionButton) {
    correctionButton.hidden = !latestForZone;
    correctionButton.disabled = state.programSimpleSaving || !latestForZone;
  }
}

function selectedCylinderEvaluationZone(result, form = $("#slip-schedule-form")) {
  const override = Number(state.programSimpleZoneOverride || 0);
  if (override) return override;
  const control = state.moldState?.zona_en_liberacion || null;
  const controlNumber = Number(control?.zona_numero || 0);
  if (
    controlNumber
    && !control?.es_zona_heredada
    && control?.hora_salida_planta
    && !latestScheduleRevisionForZone(result?.historial || [], controlNumber)
  ) {
    return controlNumber;
  }
  return Number(result?.zona_evaluacion_cilindro || result?.siguiente_zona_programa || form?.elements.start_zone?.value || 1);
}

function simpleScheduleZoneData(result, zone) {
  const layer = (result?.capas || []).find((item) => Number(item.zona_numero) === Number(zone));
  const moldZone = (state.moldState?.zonas_activas || []).find((item) => Number(item.zona_numero) === Number(zone));
  return {
    salida:
      layer?.hora_real_salida_planta
      || moldZone?.hora_salida_planta
      || (Number(result?.zona_evaluacion_cilindro) === Number(zone) ? result?.salida_planta_evaluacion : null)
      || (Number(result?.siguiente_zona_programa) === Number(zone) ? result?.salida_planta_sugerida : null),
  };
}

function latestScheduleRevisionForZone(history, zone) {
  return history
    .filter((item) => Number(item.start_zone || 1) === Number(zone))
    .slice(-1)[0] || null;
}

function simpleRevisionText(item) {
  const scenario = String(item.escenario_resuelto || item.escenario_activo || "").replace("SCENARIO_", "");
  if (scenario) return `Ultimo resultado de Zona ${item.start_zone}: paso a ${scenario}.`;
  if (item.resultado_4h === "FALLA" && item.resultado_5h === "FALLA" && item.resultado_6h === "FALLA") {
    return `Zona ${item.start_zone}: falla a 6h; requiere supervisor.`;
  }
  if (item.resultado_4h === "FALLA" && item.resultado_5h === "FALLA") return `Zona ${item.start_zone}: fallo 5h; evaluar 6h.`;
  if (item.resultado_4h === "FALLA") return `Zona ${item.start_zone}: fallo 4h; evaluar 5h.`;
  return `Zona ${item.start_zone}: pendiente de resultado.`;
}

function setSimpleButtonState(selector, visible) {
  const button = $(selector);
  if (!button) return;
  button.hidden = !visible;
  button.disabled = !visible || Boolean(state.programSimpleSaving);
}

async function saveSimpleCylinderEvaluation(result4h, result5h = "PENDIENTE", result6h = "PENDIENTE") {
  if (state.programSimpleSaving) return;
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  const form = $("#slip-schedule-form");
  const schedule = state.schedule || {};
  const zone = selectedCylinderEvaluationZone(schedule, form);
  const zoneData = simpleScheduleZoneData(schedule, zone);
  if (!zoneData.salida) {
    activateTab("captura");
    return alert(`Registra la olla de la Zona ${zone} con salida de planta antes de evaluar cilindro.`);
  }
  if (!(await confirmSuspiciousTiming({ hora_salida_planta: zoneData.salida }, { title: "Confirmar hora de evaluacion" }))) return;
  const label = simpleCylinderResultLabel(result4h, result5h, result6h);
  const confirmed = await appConfirm(
    [
      `Zona: ${zone}`,
      `Salida planta: ${formatZoneTime(zoneData.salida)}`,
      `Resultado: ${label}`,
      "",
      "Esto guardara una revision y recalculara el programa desde esta zona.",
    ].join("\n"),
    {
      title: "Confirmar resultado de cilindro",
      type: result4h === "PASA" ? "warning" : "danger",
      confirmText: "Confirmar resultado",
      cancelText: "Revisar",
    }
  );
  if (!confirmed) return;
  const payload = {
    colado_id: state.activeColadoId,
    t_fabricacion: zoneData.salida,
    start_zone: zone,
    layer_thickness_cm: Number(form?.elements.layer_thickness_cm?.value || schedule.ensayo?.layer_thickness_cm || 30),
    total_layers: Number(form?.elements.total_layers?.value || schedule.ensayo?.total_layers || 7),
    resultado_4h: result4h,
    resultado_5h: result5h,
    resultado_6h: result6h,
    operador: form?.elements.operador?.value || activeColado()?.operador || "",
    supervisor: form?.elements.supervisor?.value || "",
    observaciones: `Evaluacion rapida de cilindro desde Programa para Zona ${zone}.`,
  };
  try {
    setSimpleScheduleSaving(true, `Guardando ${label} para Zona ${zone}...`);
    const saved = await apiWithQualityConfirmation("/api/programa-deslizado/ensayo", payload, { title: "Confirmar hora de cilindro" });
    if (!saved) return;
    state.programSimpleZoneOverride = String(zone);
    await refreshSlipSchedule();
    await refreshMoldState();
    await refreshScadaState();
    showAppNotice(`Resultado guardado: Zona ${zone} - ${label}.`, "success");
  } catch (error) {
    alert("No se pudo guardar el resultado de cilindro: " + error.message);
  } finally {
    setSimpleScheduleSaving(false);
    renderSlipSchedule(state.schedule || {});
  }
}

function simpleCylinderResultLabel(result4h, result5h = "PENDIENTE", result6h = "PENDIENTE") {
  if (result4h === "PASA") return "PASA a 4h";
  if (result4h === "FALLA" && result5h === "PASA") return "FALLA 4h, PASA a 5h";
  if (result4h === "FALLA" && result5h === "FALLA" && result6h === "PASA") return "FALLA 4h/5h, PASA a 6h";
  if (result4h === "FALLA" && result5h === "FALLA" && result6h === "FALLA") return "FALLA 4h/5h/6h";
  if (result4h === "FALLA" && result5h === "FALLA") return "FALLA 4h/5h";
  if (result4h === "FALLA") return "FALLA 4h";
  return "PENDIENTE";
}

function setSimpleScheduleSaving(saving, message = "") {
  state.programSimpleSaving = Boolean(saving);
  document.querySelectorAll(".program-simple-actions button").forEach((button) => {
    button.disabled = Boolean(saving) || button.hidden;
  });
  const target = $("#program-simple-message");
  if (saving && target && message) {
    target.textContent = message;
    target.classList.remove("blocked", "saved");
  }
}

function goToNextCylinderEvaluation() {
  const next = Number(state.schedule?.zona_evaluacion_cilindro || 0);
  if (!next) return;
  state.programSimpleZoneOverride = String(next);
  renderSlipSchedule(state.schedule || {});
}

function prepareCylinderCorrection() {
  const form = $("#slip-schedule-form");
  const schedule = state.schedule || {};
  const zone = selectedCylinderEvaluationZone(schedule, form);
  const zoneData = simpleScheduleZoneData(schedule, zone);
  const latest = latestScheduleRevisionForZone(schedule.historial || [], zone);
  if (!form || !latest) return;
  form.elements.start_zone.value = String(zone);
  if (zoneData.salida) form.elements.t_fabricacion.value = toDatetimeLocalValue(zoneData.salida);
  form.elements.layer_thickness_cm.value = format(latest.layer_thickness_cm || schedule.ensayo?.layer_thickness_cm || 30, 1);
  form.elements.total_layers.value = String(latest.total_layers || schedule.ensayo?.total_layers || 7);
  form.elements.resultado_4h.value = latest.resultado_4h || "PENDIENTE";
  form.elements.resultado_5h.value = latest.resultado_5h || "PENDIENTE";
  form.elements.resultado_6h.value = latest.resultado_6h || "PENDIENTE";
  form.elements.operador.value = latest.operador || activeColado()?.operador || "";
  form.elements.supervisor.value = latest.supervisor || "";
  form.elements.observaciones.value = "";
  updateCylinderResultControls(form);
  const advanced = document.querySelector(".program-advanced-panel");
  if (advanced) advanced.open = true;
  form.scrollIntoView({ behavior: "smooth", block: "start" });
  showAppNotice(`Formulario avanzado listo para corregir Zona ${zone}. Captura motivo en Observaciones.`, "info");
}

function renderOperatorSchedule(result) {
  const target = $("#operator-schedule-card");
  if (!target) return;
  const statusEl = $("#operator-schedule-status");
  const summaryEl = $("#operator-schedule-summary");
  const programa = result?.programa || null;
  const estado = result?.estado_ensayo || {};
  if (!programa) {
    statusEl.textContent = estado.estado === "REQUIERE_SUPERVISOR" ? "Requiere supervisor" : "Sin programa";
    summaryEl.textContent = estado.mensaje || "Registra el ensayo de cilindro en Programa.";
    target.className = `operator-schedule-card ${estado.estado || ""}`;
    return;
  }
  const next = result?.resumen?.siguiente_capa || (result?.capas || []).find((layer) => !layer.hora_real_salida_planta);
  statusEl.textContent = `${programa.escenario.replace("SCENARIO_", "")}: ${format(programa.step_cm, 1)} cm / ${format(programa.step_minutes, 1)} min`;
  summaryEl.textContent = next
    ? `Siguiente: Capa ${next.capa_numero} / Zona ${next.zona_numero} objetivo ${formatZoneTime(next.hora_programada)}.`
    : "Todas las capas del programa tienen salida real registrada.";
  target.className = "operator-schedule-card ACTIVO";
}

function fillAdvanceRecipeFormFromSuggestion(suggestion) {
  const form = $("#advance-recipe-form");
  if (!form || !suggestion) return;
  form.elements.avance_objetivo_cm.value = format(suggestion.avance_objetivo_cm, 1);
  form.elements.intervalo_objetivo_min.value = format(suggestion.intervalo_objetivo_min, 1);
  syncAdvanceRecipeToleranceFields(recipeFromAdvanceForm());
  form.elements.motivo.value = suggestion.motivo || "";
  form.elements.operador.value = activeColado()?.operador || form.elements.operador.value || "";
  updateAdvanceActionLabel(recipeFromAdvanceForm(), true);
  updateAdvanceRecipeSummary(recipeFromAdvanceForm(), true);
}

async function saveSuggestedAdvanceRecipe() {
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  if (isColadoClosed()) return alert("El colado esta finalizado. Reabre el colado antes de cambiar recetas.");
  const prediction = state.moldState?.prediccion_deslizamiento || {};
  const suggestion = prediction.receta_sugerida;
  if (!suggestion) return alert("No hay una receta sugerida aplicable.");
  const active = activeAdvanceRecipe();
  const confirmed = await appConfirm(
    [
      "El sistema recomienda ajustar la receta.",
      "",
      `Actual: ${format(active.avance_objetivo_cm, 1)} cm cada ${format(active.intervalo_objetivo_min, 1)} min = ${format(active.velocidad_objetivo_cm_h, 1)} cm/h.`,
      `Sugerida: ${recipeSuggestionText(suggestion)}.`,
      "",
      prediction.motivo_recomendacion || suggestion.motivo || "",
    ].join("\n"),
    {
      title: suggestion.requiere_supervisor ? "Aplicar sugerencia con supervisor" : "Aplicar sugerencia de receta",
      type: suggestion.requiere_supervisor ? "danger" : "warning",
      confirmText: "Aplicar sugerencia",
    }
  );
  if (!confirmed) return;
  let supervisor = "";
  let motivo = suggestion.motivo || "";
  if (suggestion.requiere_supervisor) {
    supervisor = await appPrompt("Captura el supervisor responsable del ajuste.", "", {
      title: "Supervisor requerido",
      type: "danger",
      promptLabel: "Supervisor",
      confirmText: "Continuar",
    }) || "";
    if (!supervisor) return;
    motivo = await appPrompt("Captura el motivo del ajuste.", motivo, {
      title: "Motivo requerido",
      type: "danger",
      promptLabel: "Motivo",
      confirmText: "Aplicar",
    }) || "";
    if (!motivo.trim()) return;
  }
  const payload = {
    colado_id: state.activeColadoId,
    fecha_hora: formatDatetimeLocal(new Date()),
    avance_objetivo_cm: suggestion.avance_objetivo_cm,
    intervalo_objetivo_min: suggestion.intervalo_objetivo_min,
    tolerancia_velocidad_min_cm_h: suggestion.tolerancia_velocidad_min_cm_h,
    tolerancia_velocidad_max_cm_h: suggestion.tolerancia_velocidad_max_cm_h,
    motivo,
    operador: activeColado()?.operador || "",
    supervisor,
  };
  try {
    await api("/api/receta-avance", { method: "POST", body: JSON.stringify(payload) });
    fillAdvanceRecipeFormFromSuggestion(suggestion);
    await refreshMoldState();
    await refreshScadaState();
    await refreshTrends();
    alert("Receta sugerida aplicada.");
  } catch (error) {
    alert("No se pudo aplicar la receta sugerida: " + error.message);
  }
}

function renderOperatorMoldProgress(result) {
  const target = $("#operator-mold-progress");
  if (!target) return;
  const progress = result?.progreso_operativo || null;
  const advance = Math.max(0, Number(progress?.avance_total_cm ?? result?.avance_acumulado_cm ?? 0));
  const windowInfo = result?.ventana_molde || {};
  const moldHeight = Number(windowInfo.altura_molde_cm || 120);
  const zone = result?.zona_en_liberacion || null;
  const upperZone = result?.zona_superior_en_llenado || null;
  const configuredZoneHeight = Number(result?.configuracion_molde?.altura_zona_m) * 100;
  const releaseZoneHeight = zone
    ? Number(zone.elevacion_superior_cm) - Number(zone.elevacion_inferior_cm)
    : NaN;
  const upperZoneHeight = upperZone
    ? Number(upperZone.elevacion_superior_cm) - Number(upperZone.elevacion_inferior_cm)
    : NaN;
  const zoneHeight = [configuredZoneHeight, releaseZoneHeight, upperZoneHeight, 30]
    .find((value) => Number.isFinite(value) && value > 0) || 30;
  const segmentStart = Number.isFinite(Number(progress?.tramo_inicio_cm))
    ? Number(progress.tramo_inicio_cm)
    : Math.floor(advance / zoneHeight) * zoneHeight;
  const segmentEnd = Number.isFinite(Number(progress?.tramo_fin_cm))
    ? Number(progress.tramo_fin_cm)
    : segmentStart + zoneHeight;
  const segmentProgress = Number.isFinite(Number(progress?.progreso_tramo_cm))
    ? Number(progress.progreso_tramo_cm)
    : Math.max(0, Math.min(zoneHeight, advance - segmentStart));
  const segmentRemaining = Number.isFinite(Number(progress?.restante_tramo_cm))
    ? Number(progress.restante_tramo_cm)
    : Math.max(0, zoneHeight - segmentProgress);
  const progressPct = zoneHeight > 0 ? Math.max(0, Math.min(100, (segmentProgress / zoneHeight) * 100)) : 0;
  const operativeWindow = progress?.ventana_operativa || null;
  const base = Number.isFinite(Number(operativeWindow?.base_cm))
    ? Number(operativeWindow.base_cm)
    : Number.isFinite(Number(windowInfo.base_cm))
      ? Number(windowInfo.base_cm)
      : advance;
  const crown = Number.isFinite(Number(operativeWindow?.corona_cm))
    ? Number(operativeWindow.corona_cm)
    : Number.isFinite(Number(windowInfo.corona_cm))
      ? Number(windowInfo.corona_cm)
      : base + moldHeight;
  const releaseLabel = progress?.zona_liberacion_numero
    ? `Zona ${progress.zona_liberacion_numero}`
    : zone
      ? `Zona ${zone.zona_numero}`
      : "--";
  const fillLabel = progress?.zona_llenado_numero
    ? `Zona ${progress.zona_llenado_numero}`
    : upperZone
      ? `Zona ${upperZone.zona_numero}`
      : "--";

  $("#operator-total-advance").textContent = `${format(advance, 1)} cm`;
  $("#operator-current-segment").textContent = `Tramo ${format(segmentStart, 0)}-${format(segmentEnd, 0)} cm`;
  $("#operator-segment-remaining").textContent =
    segmentRemaining <= 0.001 ? "Tramo completo" : `Faltan ${format(segmentRemaining, 1)} cm`;
  const fill = $("#operator-mold-progress-fill");
  if (fill) fill.style.width = `${progressPct}%`;
  $("#operator-mold-window").textContent = `${format(base, 1)}-${format(crown, 1)} cm`;
  $("#operator-progress-release-zone").textContent = releaseLabel;
  $("#operator-progress-fill-zone").textContent = fillLabel;
}

function syncOperatorActionButton(timerState) {
  const button = $("#operator-action-btn");
  if (!button) return;
  const closed = isColadoClosed();
  const status = closed ? "CERRADO" : state.moldState?.estado_operativo || "SIN_ZONAS";
  const baseAction = operatorActionForStatus(status);
  const isTimedAction = ["slide", "slide-risk"].includes(baseAction.action);
  const waitingForTimer = isTimedAction && timerState && !timerState.ready;
  const action = waitingForTimer || timerState?.timeIssue ? "wait" : baseAction.action;
  button.dataset.baseAction = baseAction.action;
  button.dataset.action = action;
  button.textContent = timerState?.timeIssue ? "Revisar hora" : waitingForTimer ? `Esperar ${timerState.label}` : baseAction.label;
  button.classList.toggle("blocked", action === "wait");
  button.classList.toggle("risk", action === "slide-risk");
  button.classList.toggle("timer-waiting", waitingForTimer);
  button.classList.toggle("time-issue", Boolean(timerState?.timeIssue));
  button.disabled = closed;
  button.classList.toggle("closed", closed);
  const authorizeButton = $("#operator-authorize-btn");
  if (authorizeButton) {
    const zone = state.moldState?.zona_en_liberacion;
    const canRequestAuthorization = canMarkReadyByFieldCriteria(state.moldState);
    authorizeButton.hidden = closed || !canRequestAuthorization;
    authorizeButton.disabled = closed || Boolean(timerState?.timeIssue);
    authorizeButton.textContent = canRequestAuthorization
      ? `Marcar lista por inspeccion - Zona ${zone.zona_numero}`
      : "Marcar lista por inspeccion";
  }
}

function operatorMessage(result, action) {
  const zone = result?.zona_en_liberacion;
  if (action === "closed") return `Colado finalizado. ${coladoClosureText()}. Solo quedan disponibles consulta, reportes, respaldo y evidencia.`;
  if (action === "capture") return "Crea o selecciona un colado y genera zonas para iniciar.";
  if (action === "register-truck") {
    const missing = Number(result?.zonas_requeridas_iniciales || 4) - Number(result?.zonas_confirmadas_iniciales || 0);
    return `Molde incompleto: faltan ${Math.max(0, missing)} olla(s) para completar 1.20 m.`;
  }
  if (action === "wait") return zone ? `Zona ${zone.zona_numero} no esta lista para liberar.` : "El sistema bloquea el siguiente movimiento.";
  if (action === "review") return zone ? `Revisa temperatura e inspeccion de Zona ${zone.zona_numero}.` : "Captura evidencia antes de continuar.";
  if (action === "slide-risk") return zone ? `Zona ${zone.zona_numero}: avanzar solo con vigilancia.` : "Riesgo operativo activo.";
  return zone ? `Zona ${zone.zona_numero} liberable. Confirma temperatura e inspeccion.` : "Listo para deslizar.";
}

function operatorTimerState() {
  const recipe = activeAdvanceRecipe();
  const intervalMs = Math.max(0.1, Number(recipe.intervalo_objetivo_min || DEFAULT_ADVANCE_INTERVAL_MIN)) * 60000;
  const last = latestMoldAdvance();
  if (!last) {
    return {
      ready: true,
      label: "Evaluar ahora",
      stateLabel: "Listo para primera evaluacion",
      progress: 100,
      remainingMs: 0,
      elapsedMs: 0,
      targetTime: null,
      lastAdvanceTime: null,
      cycleKey: "first-evaluation",
    };
  }
  const lastTime = new Date(last.fecha_hora).getTime();
  const now = Date.now();
  if (!Number.isFinite(lastTime)) {
    return {
      ready: true,
      label: "Evaluar ahora",
      stateLabel: "Sin hora valida de ultimo avance",
      progress: 100,
      remainingMs: 0,
      elapsedMs: 0,
      targetTime: null,
      lastAdvanceTime: null,
      cycleKey: "invalid-last-advance",
    };
  }
  if (lastTime - now > 60000) {
    return {
      ready: true,
      label: "Revisar hora",
      stateLabel: `Ultimo avance en el futuro: ${formatClock(new Date(lastTime))}`,
      progress: 100,
      remainingMs: 0,
      elapsedMs: 0,
      overdueMs: 0,
      targetTime: null,
      lastAdvanceTime: new Date(lastTime),
      cycleKey: `future-${last.id || last.fecha_hora}`,
      timeIssue: true,
    };
  }
  const target = lastTime + intervalMs;
  const remainingMs = Math.max(0, target - now);
  const elapsedMs = Math.max(0, now - lastTime);
  const cycleKey = `${last.id || last.fecha_hora}|${target}`;
  if (remainingMs <= 0) {
    const overdueMs = Math.max(0, now - target);
    return {
      ready: true,
      label: "Evaluar ahora",
      stateLabel: `${timerReadyLabel()} - vencido hace ${formatTimerDuration(overdueMs)}`,
      progress: 100,
      remainingMs: 0,
      elapsedMs,
      overdueMs,
      targetTime: new Date(target),
      lastAdvanceTime: new Date(lastTime),
      cycleKey,
    };
  }
  const totalSeconds = Math.ceil(remainingMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return {
    ready: false,
    label: `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`,
    stateLabel: remainingMs <= 60000 ? "Menos de 1 minuto" : "Cuenta regresiva activa",
    progress: clampTimerProgress((elapsedMs / intervalMs) * 100),
    remainingMs,
    elapsedMs,
    overdueMs: 0,
    targetTime: new Date(target),
    lastAdvanceTime: new Date(lastTime),
    cycleKey,
  };
}

function formatTimerDuration(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function timerReadyLabel() {
  const status = state.moldState?.estado_operativo || "SIN_ZONAS";
  if (status === "MOLDE_INCOMPLETO") return "Evaluar ahora - registrar olla";
  if (status === "NO_LIBERAR" || status === "FALTA_ZONA_SUPERIOR") return "Evaluar ahora - esperar";
  if (status === "PREPARARSE") return "Evaluar ahora - revisar";
  return "Toca evaluar";
}

function clampTimerProgress(value) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function updateOperatorTimer() {
  const timer = $("#operator-timer");
  const bar = $("#operator-timer-progress");
  if (!timer || !bar) return;
  if (isColadoClosed()) {
    const timerCard = timer.closest(".operator-timer-card");
    timer.textContent = "Finalizado";
    timer.classList.remove("ready");
    timerCard?.classList.remove("operator-timer-ready", "operator-timer-soon", "operator-timer-blocked");
    timerCard?.classList.add("operator-timer-closed");
    bar.style.width = "100%";
    const stateLabel = $("#operator-timer-state");
    if (stateLabel) stateLabel.textContent = coladoClosureText();
    const lastLabel = $("#operator-last-advance-time");
    const last = latestMoldAdvance();
    if (lastLabel) lastLabel.textContent = last?.fecha_hora ? `Ultimo avance: ${formatZoneTime(last.fecha_hora)}` : "Ultimo avance: --";
    const nextLabel = $("#operator-next-time");
    if (nextLabel) nextLabel.textContent = "Siguiente: no aplica";
    syncOperatorActionButton({ ready: true, label: "Finalizado" });
    return;
  }
  const current = operatorTimerState();
  const timerCard = timer.closest(".operator-timer-card");
  timer.textContent = current.label;
  timer.classList.toggle("ready", current.ready);
  timerCard?.classList.toggle("operator-timer-ready", current.ready);
  timerCard?.classList.toggle("operator-timer-soon", !current.ready && current.remainingMs <= 60000);
  timerCard?.classList.toggle("operator-timer-blocked", current.ready && ["NO_LIBERAR", "FALTA_ZONA_SUPERIOR", "MOLDE_INCOMPLETO"].includes(state.moldState?.estado_operativo || ""));
  bar.style.width = `${format(current.progress, 0)}%`;
  const stateLabel = $("#operator-timer-state");
  if (stateLabel) stateLabel.textContent = current.stateLabel;
  const lastLabel = $("#operator-last-advance-time");
  if (lastLabel) lastLabel.textContent = current.lastAdvanceTime ? `Ultimo avance: ${formatClock(current.lastAdvanceTime)}` : "Ultimo avance: --";
  const nextLabel = $("#operator-next-time");
  if (nextLabel) nextLabel.textContent = current.targetTime ? `Siguiente: ${formatClock(current.targetTime)}` : "Siguiente: ahora";
  updateOperatorCommandBar({
    advanceText: $("#operator-total-advance")?.textContent || "0.0 cm",
    nextText: current.targetTime ? formatClock(current.targetTime) : "Ahora",
  });
  syncOperatorActionButton(current);
  maybeRefreshOperatorAtZero(current);
}

function formatClock(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return "--";
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function activeTabName() {
  return document.querySelector(".tab-button.active")?.dataset.tab || "";
}

function startOperatorLoop() {
  state.operatorLoop = state.operatorLoop || {};
  if (state.operatorLoop.intervalId) return;
  state.operatorLoop.lastPassiveRefreshAt = 0;
  state.operatorLoop.refreshedReadyCycles = {};
  state.operatorLoop.intervalId = window.setInterval(() => {
    updateOperatorTimer();
    const tab = activeTabName();
    if (tab !== "operador") return;
    const now = Date.now();
    if (now - Number(state.operatorLoop.lastPassiveRefreshAt || 0) >= 30000) {
      state.operatorLoop.lastPassiveRefreshAt = now;
      if (tab === "operador") refreshOperatorStateSilently();
      else refreshTrends();
    }
  }, 1000);
}

async function refreshOperatorStateSilently() {
  if (!state.activeColadoId) return;
  try {
    state.moldState = await api(moldStateUrl({ useEvaluationTime: false }));
    renderMoldState(state.moldState);
    await refreshOperatorTrendsSilently();
    setConnection("En linea", true);
  } catch (error) {
    setConnection("Sin conexion", false);
    const warning = $("#operator-warning");
    if (warning) {
      warning.textContent = "Sin conexion: revisar servidor.";
      warning.classList.add("active");
    }
  }
}

function maybeRefreshOperatorAtZero(timerState) {
  if (!timerState.ready || !timerState.cycleKey || !state.activeColadoId) return;
  state.operatorLoop = state.operatorLoop || { refreshedReadyCycles: {} };
  state.operatorLoop.refreshedReadyCycles = state.operatorLoop.refreshedReadyCycles || {};
  if (state.operatorLoop.refreshedReadyCycles[timerState.cycleKey]) return;
  state.operatorLoop.refreshedReadyCycles[timerState.cycleKey] = true;
  if (activeTabName() === "operador") refreshOperatorStateSilently();
}

function renderScadaState(result) {
  setFieldCommandState(state.moldState);
  renderOperationalGuidance();
  renderOperatorTab(state.moldState);
}

const {
  renderZoneSelectors,
  renderOperatorLiveTrend,
  renderReadings,
} = window.SlipformOperatorView;

function renderZonesTable(zones) {
  $("#zones-table").innerHTML =
    zones.length === 0
      ? `<tr><td colspan="10">Sin zonas.</td></tr>`
      : zones
          .map(
            (z) => `<tr>
              <td>${escapeHtml(z.zona_numero)}</td>
              <td>${escapeHtml(z.es_zona_heredada ? "Sin olla" : z.numero_olla || z.zona_numero || "--")}</td>
              <td>${z.es_zona_heredada ? "0.0 m3" : `${format(z.volumen_olla_m3 || z.volumen_m3 || 5, 1)} m3`}</td>
              <td>${format(z.elevacion_inferior_cm, 0)}-${format(z.elevacion_superior_cm, 0)} cm</td>
              <td>${escapeHtml(z.es_zona_heredada ? "Existente previo" : formatZoneTime(z.hora_salida_planta || z.hora_referencia_madurez))}</td>
              <td>${escapeHtml(formatZoneTime(z.hora_inicio_descarga || z.hora_inicio_llenado))}</td>
              <td>${format(z.edad_real_h, 2)} h</td>
              <td>${format(z.avance_madurez * 100, 1)}%</td>
              <td>${escapeHtml(z.es_zona_heredada ? "existente_previo" : z.origen_generacion || "manual")}</td>
              <td>${escapeHtml(z.es_zona_heredada ? "Lista por campo" : z.estado_zona)}</td>
            </tr>`
          )
          .join("");
}

function renderTruckLoadsTable() {
  const table = $("#truck-loads-table");
  if (!table) return;
  const rows = state.operationalData.descargas || [];
  const zonesByLoad = new Map((state.moldState?.zonas_activas || []).map((zone) => [String(zone.descarga_olla_id || ""), zone]));
  table.innerHTML =
    rows.length === 0
      ? `<tr><td colspan="10">Sin ollas. Registra la Olla 1 para crear la Zona 1.</td></tr>`
      : rows
          .map((load) => {
            const zone = zonesByLoad.get(String(load.id));
            return `<tr data-descarga-id="${escapeHtml(load.id)}">
              <td><input name="numero_olla" value="${escapeHtml(load.numero_olla || "")}" /></td>
              <td>${zone ? `Zona ${escapeHtml(zone.zona_numero)}` : "--"}</td>
              <td><input name="volumen_m3" type="number" step="0.1" min="0.1" value="${escapeHtml(load.volumen_m3 || 5)}" /></td>
              <td><input name="hora_salida_planta" type="datetime-local" value="${toDatetimeLocalValue(load.hora_salida_planta)}" /></td>
              <td><input name="hora_llegada_obra" type="datetime-local" value="${toDatetimeLocalValue(load.hora_llegada_obra)}" /></td>
              <td><input name="hora_inicio_descarga" type="datetime-local" value="${toDatetimeLocalValue(load.hora_inicio_descarga)}" /></td>
              <td><input name="hora_fin_descarga" type="datetime-local" value="${toDatetimeLocalValue(load.hora_fin_descarga)}" /></td>
              <td><input name="temperatura_llegada_c" type="number" step="0.1" value="${escapeHtml(load.temperatura_llegada_c ?? "")}" /></td>
              <td><input name="revenimiento_cm" type="number" step="0.1" value="${escapeHtml(load.revenimiento_cm ?? "")}" /></td>
              <td><button type="button" class="button-small save-truck-load-btn">Guardar</button><small>${escapeHtml(load.estado_operativo || "CONFIRMADA")}</small></td>
            </tr>`;
          })
          .join("");
}

function updateTruckZoneFormDefaults(force = false) {
  const form = $("#truck-zone-form");
  if (!form) return;
  const existingNumbers = (state.operationalData.descargas || [])
    .map((load) => Number(load.numero_olla))
    .filter(Number.isFinite);
  const zoneNumbers = (state.moldState?.zonas_activas || [])
    .map((zone) => Number(zone.zona_numero))
    .filter(Number.isFinite);
  const allNumbers = [...existingNumbers, ...zoneNumbers];
  const nextNumber = allNumbers.length ? Math.max(...allNumbers) + 1 : 1;
  const numberInput = form.elements.numero_olla;
  if (force || !numberInput.value || Number(numberInput.value) === Number(form.dataset.autofillNumber || 0)) {
    numberInput.value = String(nextNumber);
    form.dataset.autofillNumber = String(nextNumber);
  }
  if (!form.elements.volumen_m3.value) form.elements.volumen_m3.value = "5";
}

function initialMoldPendingZoneNumbers() {
  const required = (state.moldState?.zonas_requeridas_molde || [])
    .map((number) => Number(number))
    .filter(Number.isFinite);
  const existing = new Set(
    (state.moldState?.zonas_activas || [])
      .map((zone) => Number(zone.zona_numero))
      .filter(Number.isFinite)
  );
  const missing = required.filter((number) => !existing.has(number));
  if (missing.length) return missing;
  const cfg = state.moldState?.configuracion_molde || {};
  const zonesPerMold = Math.max(1, Number(cfg.zonas_por_molde || 4));
  const next = [...existing].length ? Math.max(...existing) + 1 : 1;
  return Array.from({ length: zonesPerMold }, (_, index) => next + index);
}

function updateZoneGeneratorSummary() {
  const form = $("#zone-generator-form");
  if (!form) return;
  const pending = initialMoldPendingZoneNumbers();
  const summary = $("#zone-generator-summary");
  const button = $("#zone-generator-submit");
  const first = pending[0] || 1;
  const count = pending.length || 4;
  if (summary) {
    summary.textContent =
      count === 4 && first === 1
        ? "Arranque normal: se planifican Zonas 1-4."
        : `Se planificaran ${count} olla(s): Zona ${pending.join(", Zona ")}.`;
  }
  if (button) {
    button.textContent =
      count === 4 && first === 1
        ? "Planificar 4 Ollas / Zonas"
        : `Planificar ${count} Olla(s) Pendiente(s)`;
  }
}

function updateStartOffsetSummary() {
  const form = $("#start-offset-form");
  if (!form) return;
  if (form.elements.hora_inicio_operativo && !form.elements.hora_inicio_operativo.value) {
    form.elements.hora_inicio_operativo.value = formatDatetimeLocal(new Date());
  }
  const first = Math.max(1, Number(form.elements.primera_zona_nueva.value || 1));
  const cfg = state.moldState?.configuracion_molde || {};
  const zonesPerMold = Math.max(1, Number(cfg.zonas_por_molde || 4));
  const zoneHeightCm = Math.max(1, Number(cfg.altura_zona_m || 0.3) * 100);
  const baseCm = Math.max(0, (first - zonesPerMold) * zoneHeightCm);
  const crownCm = baseCm + zonesPerMold * zoneHeightCm;
  const firstPrevious = Math.max(1, first - zonesPerMold + 1);
  const previousNumbers = [];
  for (let number = firstPrevious; number < first; number += 1) previousNumbers.push(number);
  const previous = Math.max(0, first - 1);
  form.elements.zonas_previas_existentes.value = String(previous);
  const recognizedCount = previousNumbers.length;
  const summary = $("#start-offset-summary");
  if (summary) {
    summary.textContent = previous
      ? `Primera zona nueva: Zona ${first}. Base inicial ${format(baseCm, 1)} cm; molde ${format(baseCm, 1)}-${format(crownCm, 1)} cm. Previas activas en molde: ${recognizedCount ? `Zona ${previousNumbers.join(", Zona ")}` : "ninguna"}.`
      : "Arranque normal: la primera olla crea Zona 1.";
  }
  const supervisor = form.elements.supervisor;
  if (supervisor) supervisor.required = previous > 0;
}

async function confirmSuspiciousTiming(payload, options = {}) {
  const warnings = suspiciousTimingWarnings(payload, options);
  if (!warnings.length) return true;
  markTimingWarningFields(options.form, warnings);
  const ok = await appConfirm(
    [
      ...warnings.map((item) => `- ${item.text}`),
      "",
      "Estos horarios afectan madurez, programa y reportes.",
      "Continua solo si ya verificaste el dato en campo.",
    ].join("\n"),
    {
      title: options.title || "Confirmar horarios sospechosos",
      type: "warning",
      confirmText: "Guardar de todos modos",
      cancelText: "Corregir",
    }
  );
  if (!ok) showAppNotice("Corrige los horarios marcados antes de guardar.", "error");
  if (ok) payload.confirmar_horario_sospechoso = true;
  return ok;
}

async function apiWithQualityConfirmation(path, payload, options = {}) {
  try {
    return await api(path, { method: options.method || "POST", body: JSON.stringify(payload) });
  } catch (error) {
    if (error.status !== 409 || !error.body?.requiere_confirmacion) throw error;
    const warnings = error.body.advertencias || [];
    const ok = await appConfirm(
      [
        ...warnings.map((item) => `- ${item.message || item.text || item.code}`),
        "",
        "El backend requiere confirmacion antes de guardar estos datos.",
      ].join("\n"),
      {
        title: options.title || "Confirmar datos criticos",
        type: "warning",
        confirmText: "Guardar de todos modos",
        cancelText: "Corregir",
      }
    );
    if (!ok) return null;
    payload.confirmar_horario_sospechoso = true;
    return api(path, { method: options.method || "POST", body: JSON.stringify(payload) });
  }
}

function suspiciousTimingWarnings(payload, options = {}) {
  const warnings = [];
  const fields = {
    hora_salida_planta: parseLocalDateTime(payload.hora_salida_planta),
    hora_llegada_obra: parseLocalDateTime(payload.hora_llegada_obra),
    hora_inicio_descarga: parseLocalDateTime(payload.hora_inicio_descarga),
    hora_fin_descarga: parseLocalDateTime(payload.hora_fin_descarga),
  };
  const futureLimit = new Date(Date.now() + 15 * 60000);
  Object.entries(fields).forEach(([name, value]) => {
    if (value && value > futureLimit) {
      warnings.push({
        field: name,
        text: `${timingFieldLabel(name)} esta en el futuro: ${formatZoneTime(payload[name])}.`,
      });
    }
  });
  addChronologyWarning(warnings, fields, payload, "hora_salida_planta", "hora_llegada_obra");
  addChronologyWarning(warnings, fields, payload, "hora_llegada_obra", "hora_inicio_descarga");
  addChronologyWarning(warnings, fields, payload, "hora_inicio_descarga", "hora_fin_descarga");
  addTruckSequenceWarnings(warnings, payload, options);
  return warnings;
}

function addChronologyWarning(warnings, fields, payload, firstName, secondName) {
  const first = fields[firstName];
  const second = fields[secondName];
  if (!first || !second || second >= first) return;
  warnings.push({
    field: secondName,
    text: `${timingFieldLabel(secondName)} (${formatZoneTime(payload[secondName])}) es anterior a ${timingFieldLabel(firstName)} (${formatZoneTime(payload[firstName])}).`,
  });
}

function addTruckSequenceWarnings(warnings, payload, options = {}) {
  const number = Number(payload.numero_olla);
  const departure = parseLocalDateTime(payload.hora_salida_planta);
  if (!Number.isFinite(number) || !departure) return;
  const currentLoadId = String(options.descargaId || payload.id || "");
  const loads = (state.operationalData?.descargas || [])
    .filter((load) => !currentLoadId || String(load.id || "") !== currentLoadId)
    .map((load) => ({
      number: Number(load.numero_olla),
      departure: parseLocalDateTime(load.hora_salida_planta),
    }))
    .filter((load) => Number.isFinite(load.number) && load.departure);
  const previous = loads
    .filter((load) => load.number < number)
    .sort((a, b) => b.number - a.number)[0];
  const next = loads
    .filter((load) => load.number > number)
    .sort((a, b) => a.number - b.number)[0];
  if (previous && departure < previous.departure) {
    warnings.push({
      field: "hora_salida_planta",
      text: `La salida de Olla ${number} es anterior a la Olla ${previous.number}. Revisa la secuencia.`,
    });
  }
  if (next && departure > next.departure) {
    warnings.push({
      field: "hora_salida_planta",
      text: `La salida de Olla ${number} es posterior a la Olla ${next.number}. Revisa la secuencia.`,
    });
  }
}

function markTimingWarningFields(form, warnings) {
  if (!form) return;
  const names = new Set(warnings.map((item) => item.field).filter(Boolean));
  names.forEach((name) => {
    const field = form.querySelector?.(`[name="${name}"]`) || form.elements?.[name];
    if (field) markInvalidField(field);
  });
}

function parseLocalDateTime(value) {
  if (!value) return null;
  const date = new Date(String(value).replace(" ", "T"));
  return Number.isNaN(date.getTime()) ? null : date;
}

function timingFieldLabel(name) {
  return {
    hora_salida_planta: "Salida planta",
    hora_llegada_obra: "Llegada obra",
    hora_inicio_descarga: "Inicio descarga",
    hora_fin_descarga: "Fin descarga",
  }[name] || name;
}

async function initializeStartOffsetFromForm(form) {
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  if (isColadoClosed()) return alert("El colado esta finalizado. Reabre el colado antes de inicializar arranque.");
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.colado_id = state.activeColadoId;
  payload.operador = payload.operador || activeColado()?.operador || "";
  if (!payload.motivo) payload.motivo = "Arranque con zona previa existente";
  const cfg = state.moldState?.configuracion_molde || {};
  const firstNewZone = Math.max(1, Number(payload.primera_zona_nueva || 1));
  const zonesPerMold = Math.max(1, Number(cfg.zonas_por_molde || 4));
  const firstPrevious = Math.max(1, firstNewZone - zonesPerMold + 1);
  const previous = Math.max(0, firstNewZone - 1);
  const previousNumbers = [];
  for (let number = firstPrevious; number < firstNewZone; number += 1) previousNumbers.push(number);
  const recognizedCount = previousNumbers.length;
  if (previous > 0) {
    const ok = await appConfirm(
      `Se reconocera${recognizedCount > 1 ? "n" : ""} ${recognizedCount} zona(s) previa(s) dentro de la ventana activa del molde. Referencia visual: Zona ${previousNumbers.join(", Zona ")}. Esta accion queda en auditoria.`,
      {
        title: "Inicializar arranque",
        type: "warning",
        confirmText: "Inicializar",
      }
    );
    if (!ok) return;
  }
  try {
    const result = await api("/api/colados/inicializar-arranque", { method: "POST", body: JSON.stringify(payload) });
    showAppNotice(
      previous
        ? `Arranque inicializado. Zonas previas activas: ${result.zonas_previas_numeros?.join(", ") || recognizedCount}. Siguiente olla sugerida: ${result.siguiente_olla_sugerida}.`
        : "Arranque normal confirmado.",
      "success"
    );
    await refreshMoldState();
    await refreshScadaState();
    await refreshTrends();
    await refreshOperationalData();
    await refreshSlipSchedule();
    updateTruckZoneFormDefaults(true);
    updateZoneGeneratorSummary();
  } catch (error) {
    alert("No se pudo inicializar el arranque: " + error.message);
  }
}

async function registerTruckZoneFromForm(form) {
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  if (isColadoClosed()) return alert("El colado esta finalizado. Reabre el colado antes de registrar ollas.");
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.colado_id = state.activeColadoId;
  payload.mezcla_id = activeColado()?.mezcla_id || "";
  payload.curva_id = activeColado()?.curva_id || "";
  if (!(await confirmSuspiciousTiming(payload, { form, title: "Confirmar horarios de olla" }))) return;
  const requestedNumber = Number(payload.numero_olla);
  const existingInherited = (state.moldState?.zonas_activas || []).find(
    (zone) => Number(zone.zona_numero) === requestedNumber && zone.es_zona_heredada
  );
  if (existingInherited) {
    const ok = await appConfirm(
      `La Zona ${requestedNumber} esta marcada como existente previa. Si continuas, se reemplazara por la olla registrada de este colado.`,
      {
        title: "Reemplazar zona previa",
        type: "warning",
        confirmText: "Reemplazar",
      }
    );
    if (!ok) return;
    payload.reemplazar_zona_heredada = true;
  }
  try {
    const result = await apiWithQualityConfirmation("/api/ollas/registrar-zona", payload, { title: "Confirmar horarios de olla" });
    if (!result) return;
    if (state.evaluationTime) setEvaluationTime("");
    showAppNotice(
      `Olla ${result.zona?.numero_olla || payload.numero_olla} registrada. Zona ${result.zona?.zona_numero || payload.numero_olla} lista para seguimiento.`,
      "success"
    );
    form.reset();
    await refreshMoldState();
    await refreshScadaState();
    await refreshTrends();
    await refreshOperationalData();
    updateTruckZoneFormDefaults(true);
  } catch (error) {
    alert("No se pudo registrar la olla/zona: " + error.message);
  }
}

async function saveTruckLoadRow(row, button) {
  if (isColadoClosed()) return alert("El colado esta finalizado. Reabre el colado antes de corregir ollas.");
  const descargaId = row.dataset.descargaId;
  if (!descargaId) return;
  const payload = {};
  row.querySelectorAll("input[name]").forEach((input) => {
    payload[input.name] = input.value;
  });
  if (!(await confirmSuspiciousTiming(payload, { form: row, title: "Confirmar correccion de olla", descargaId }))) return;
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = "Guardando";
  try {
    const updated = await apiWithQualityConfirmation(`/api/descargas/${descargaId}`, payload, {
      method: "PUT",
      title: "Confirmar correccion de olla",
    });
    if (!updated) return;
    showAppNotice("Olla actualizada. La madurez de su zona se recalculo desde salida de planta.", "success");
    await refreshMoldState();
    await refreshScadaState();
    await refreshTrends();
    await refreshOperationalData();
    await refreshSlipSchedule();
  } catch (error) {
    alert("No se pudo actualizar la olla: " + error.message);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

function renderAdvancesTable(advances) {
  $("#advances-table").innerHTML =
    advances.length === 0
      ? `<tr><td colspan="6">Sin avances registrados.</td></tr>`
      : advances
          .slice()
          .reverse()
          .map(
            (a) => `<tr>
              <td>${escapeHtml(a.fecha_hora)}</td>
              <td>${format(a.avance_cm, 1)} cm</td>
              <td>${format(a.intervalo_minutos, 1)} min</td>
              <td>${format(a.avance_acumulado_cm, 1)} cm</td>
              <td>${format(a.velocidad_real_cm_h, 1)} cm/h</td>
              <td>${escapeHtml(a.operador)}</td>
            </tr>`
          )
          .join("");
}

$("#mezcla-select")?.addEventListener("change", renderCurveOptions);

$("#colado-form select[name='estado']")?.addEventListener("change", (event) => {
  const form = $("#colado-form");
  if (!form) return;
  if (String(event.target.value || "").toUpperCase() === "CERRADO" && !form.elements.fecha_cierre.value) {
    form.elements.fecha_cierre.value = formatDatetimeLocal(new Date());
  }
});

$("#colado-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = coladoFormPayload();
  try {
    const result = await api("/api/colados", { method: "POST", body: JSON.stringify(data) });
    state.activeColadoId = String(result.id);
    localStorage.setItem("activeColadoId", state.activeColadoId);
    await loadBootstrap();
  } catch (error) {
    alert("No se pudo crear el colado: " + error.message);
  }
});

$("#colado-select")?.addEventListener("change", async (event) => {
  state.activeColadoId = event.target.value;
  if (state.activeColadoId) {
    localStorage.setItem("activeColadoId", state.activeColadoId);
  } else {
    localStorage.removeItem("activeColadoId");
  }
  populateColadoForm();
  updateColadoActionState();
  updateLinks();
  await refreshPrediction();
  await refreshMoldState();
  await refreshScadaState();
  await refreshTrends();
  await refreshSlipSchedule();
  await refreshOperationalData();
});

$("#apply-evaluation-time-btn")?.addEventListener("click", async () => {
  setEvaluationTime($("#evaluation-time").value);
  await refreshMoldState();
  await refreshScadaState();
  await refreshTrends();
});

$("#use-current-time-btn")?.addEventListener("click", async () => {
  setEvaluationTime("");
  await refreshMoldState();
  await refreshScadaState();
  await refreshTrends();
});

$("#evaluation-plus-5-btn")?.addEventListener("click", async () => {
  addEvaluationMinutes(5);
  await refreshMoldState();
  await refreshScadaState();
  await refreshTrends();
});

$("#evaluation-plus-30-btn")?.addEventListener("click", async () => {
  addEvaluationMinutes(30);
  await refreshMoldState();
  await refreshScadaState();
  await refreshTrends();
});

$("#evaluation-plus-60-btn")?.addEventListener("click", async () => {
  addEvaluationMinutes(60);
  await refreshMoldState();
  await refreshScadaState();
  await refreshTrends();
});

$("#field-mode-toggle")?.addEventListener("click", () => {
  const mode = localStorage.getItem("scadaViewMode") || "campo";
  localStorage.setItem("scadaViewMode", mode === "diagnostico" ? "campo" : "diagnostico");
  applyFieldMode();
});

$("#update-colado-btn")?.addEventListener("click", async () => {
  if (!state.activeColadoId) return alert("Selecciona un colado para editar.");
  const payload = coladoFormPayload();
  const current = activeColado();
  if (String(payload.estado || "").toUpperCase() === "CERRADO") {
    if (!payload.fecha_cierre) {
      alert("Captura la fecha de cierre para marcar el colado como cerrado.");
      return;
    }
    const closingChanged = String(current?.fecha_cierre || "").slice(0, 16) !== String(payload.fecha_cierre || "").slice(0, 16);
    const closingNow = !isColadoClosed(current);
    if (
      (closingNow || closingChanged) &&
      !(await appConfirm(
        `El colado quedara finalizado con fecha ${formatZoneTime(payload.fecha_cierre)}. Las acciones operativas quedaran bloqueadas.`,
        { title: "Cerrar colado", confirmText: closingNow ? "Cerrar colado" : "Actualizar cierre" }
      ))
    ) return;
  } else if (isColadoClosed(current)) {
    if (
      !(await appConfirm("El colado esta cerrado. Guardar este cambio lo reabrira para operacion.", {
        title: "Reabrir colado",
        confirmText: "Reabrir",
      }))
    ) return;
  }
  try {
    await api(`/api/colados/${state.activeColadoId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    await loadBootstrap();
    alert("Colado actualizado.");
  } catch (error) {
    alert("No se pudo actualizar el colado: " + error.message);
  }
});

$("#delete-colado-btn")?.addEventListener("click", async () => {
  const colado = activeColado();
  if (!colado) return alert("Selecciona un colado para eliminar.");
  const label = `#${colado.id} ${colado.silo_id || ""}`.trim();
  if (
    !(await appConfirm(`Eliminar ${label}?\nSe borraran tambien sus lecturas, zonas, avances, eventos y predicciones.`, {
      title: "Eliminar colado",
      type: "danger",
      confirmText: "Eliminar colado",
    }))
  ) {
    return;
  }
  try {
    await api(`/api/colados/${state.activeColadoId}`, { method: "DELETE" });
    clearActiveColado();
    await loadBootstrap();
    alert("Colado eliminado.");
  } catch (error) {
    alert("No se pudo eliminar el colado: " + error.message);
  }
});

$("#lectura-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  const payload = Object.fromEntries(new FormData(event.target).entries());
  payload.colado_id = state.activeColadoId;
  payload.fecha_hora = formatDatetimeLocal(new Date());
  payload.minuto_transcurrido = payload.minuto_transcurrido || autoMinute(payload.fecha_hora) || "";
  try {
    await api("/api/lecturas", { method: "POST", body: JSON.stringify(payload) });
    rememberLocalReading(payload);
    event.target.reset();
  } catch (error) {
    queueOffline("/api/lecturas", payload);
    rememberLocalReading(payload);
  }
  await refreshPrediction();
  await loadBootstrap();
});

$("#zone-reading-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  const payload = Object.fromEntries(new FormData(event.target).entries());
  if (!payload.zona_colado_id) return alert("Selecciona una zona.");
  payload.fecha_hora = payload.fecha_hora || state.evaluationTime || formatDatetimeLocal(new Date());
  try {
    await api("/api/lecturas-zona", { method: "POST", body: JSON.stringify(payload) });
    event.target.reset();
    await refreshMoldState();
    await refreshScadaState();
    await refreshTrends();
  } catch (error) {
    if (error.status) {
      alert("No se pudo guardar la lectura de zona: " + error.message);
    } else {
      queueOffline("/api/lecturas-zona", payload);
      alert("Sin conexion: la lectura de zona quedo pendiente de sincronizar.");
    }
  }
});

$("#evento-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  const form = event.target;
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.colado_id = state.activeColadoId;
  payload.fecha_hora = formatDatetimeLocal(new Date());
  payload.minuto_transcurrido = payload.minuto_transcurrido || autoMinute(payload.fecha_hora) || "";
  if (payload.decision_tomada === "DESLIZAR" && !slideChecklistOk(payload)) {
    alert("Para DESLIZAR confirma todo el checklist fisico.");
    return;
  }
  try {
    await api("/api/eventos", { method: "POST", body: JSON.stringify(payload) });
    form.reset();
  } catch (error) {
    queueOffline("/api/eventos", payload);
  }
  await refreshPrediction();
  await refreshMoldState();
});

$("#truck-zone-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  await registerTruckZoneFromForm(event.target);
});

$("#start-offset-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  await initializeStartOffsetFromForm(event.target);
});

$("#start-offset-form")?.addEventListener("input", updateStartOffsetSummary);

$("#zone-generator-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  if (isColadoClosed()) return alert("El colado esta finalizado. Reabre el colado antes de planificar ollas.");
  const payload = Object.fromEntries(new FormData(event.target).entries());
  const useZoneTimeAsEvaluation = payload.usar_hora_zona_como_evaluacion === "on";
  delete payload.usar_hora_zona_como_evaluacion;
  payload.colado_id = state.activeColadoId;
  payload.mezcla_id = activeColado()?.mezcla_id || "";
  payload.curva_id = activeColado()?.curva_id || "";
  payload.hora_salida_planta_olla_1 = payload.hora_zona_1;
  const pendingZones = initialMoldPendingZoneNumbers();
  if (pendingZones.length) {
    payload.zona_inicial = pendingZones[0];
    payload.zonas = pendingZones.length;
  }
  try {
    const result = await api("/api/zonas/generar", { method: "POST", body: JSON.stringify(payload) });
    if (useZoneTimeAsEvaluation) setEvaluationTime(payload.hora_zona_1);
    alert(`Plan de ollas creado: ${result.zonas_generadas} zonas/ollas.`);
    await refreshMoldState();
    await refreshScadaState();
    await refreshTrends();
    await refreshOperationalData();
  } catch (error) {
    alert("No se pudieron generar zonas: " + error.message);
  }
});

$("#refresh-truck-loads-btn")?.addEventListener("click", refreshOperationalData);

$("#truck-loads-table")?.addEventListener("click", async (event) => {
  const button = event.target.closest(".save-truck-load-btn");
  if (!button) return;
  const row = button.closest("tr[data-descarga-id]");
  if (!row) return;
  await saveTruckLoadRow(row, button);
});

$("#advance-recipe-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  if (isColadoClosed()) return alert("El colado esta finalizado. Reabre el colado antes de cambiar recetas.");
  const formValues = Object.fromEntries(new FormData(event.target).entries());
  const recipe = recipeFromAdvanceForm();
  const payload = {
    ...formValues,
    colado_id: state.activeColadoId,
    fecha_hora: state.evaluationTime || formatDatetimeLocal(new Date()),
    avance_objetivo_cm: recipe.avance_objetivo_cm,
    intervalo_objetivo_min: recipe.intervalo_objetivo_min,
    tolerancia_velocidad_min_cm_h: recipe.tolerancia_velocidad_min_cm_h,
    tolerancia_velocidad_max_cm_h: recipe.tolerancia_velocidad_max_cm_h,
  };
  try {
    await api("/api/receta-avance", { method: "POST", body: JSON.stringify(payload) });
    await refreshMoldState();
    await refreshScadaState();
    await refreshTrends();
    alert("Receta de avance guardada.");
  } catch (error) {
    alert("No se pudo guardar la receta: " + error.message);
  }
});

$("#advance-recipe-form")?.addEventListener("input", (event) => {
  const preview = recipeFromAdvanceForm();
  if (["avance_objetivo_cm", "intervalo_objetivo_min"].includes(event.target?.name || "")) {
    syncAdvanceRecipeToleranceFields(preview);
  }
  updateAdvanceActionLabel(preview, true);
  updateAdvanceRecipeSummary(preview, true);
});

$("#operator-apply-speed-recipe-btn")?.addEventListener("click", saveSuggestedAdvanceRecipe);

$("#slip-schedule-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  if (isColadoClosed()) return alert("El colado esta finalizado. Reabre el colado antes de cambiar el programa.");
  const payload = Object.fromEntries(new FormData(event.target).entries());
  payload.colado_id = state.activeColadoId;
  payload.operador = payload.operador || activeColado()?.operador || "";
  if (!(await confirmSuspiciousTiming({ hora_salida_planta: payload.t_fabricacion }, { form: event.target, title: "Confirmar hora de ensayo" }))) return;
  const zone = Number(payload.start_zone || 1);
  const label = simpleCylinderResultLabel(payload.resultado_4h, payload.resultado_5h, payload.resultado_6h);
  const previous = latestScheduleRevisionForZone(state.schedule?.historial || [], zone);
  if (previous && !String(payload.observaciones || "").trim()) {
    const reason = await appPrompt("Captura el motivo de correccion para guardar una nueva revision.", "", {
      title: "Motivo requerido",
      type: "warning",
      promptLabel: "Motivo",
      confirmText: "Continuar",
    });
    if (!reason || !reason.trim()) return;
    payload.observaciones = `Correccion manual: ${reason.trim()}`;
  }
  const confirmed = await appConfirm(
    [
      `Zona: ${zone}`,
      `Salida planta: ${formatZoneTime(payload.t_fabricacion)}`,
      `Resultado: ${label}`,
      previous ? "Tipo: correccion con nueva revision." : "Tipo: nueva evaluacion.",
      "",
      "Esto recalculara el programa desde la zona indicada.",
    ].join("\n"),
    {
      title: previous ? "Confirmar correccion de cilindro" : "Confirmar ensayo de cilindro",
      type: previous ? "warning" : "info",
      confirmText: previous ? "Guardar correccion" : "Guardar ensayo",
      cancelText: "Revisar",
    }
  );
  if (!confirmed) return;
  try {
    const saved = await apiWithQualityConfirmation("/api/programa-deslizado/ensayo", payload, { title: "Confirmar ensayo de cilindro" });
    if (!saved) return;
    state.programSimpleZoneOverride = String(zone);
    await refreshSlipSchedule();
    showAppNotice(previous ? `Correccion guardada para Zona ${zone}.` : "Ensayo de cilindro guardado.", "success");
  } catch (error) {
    alert("No se pudo guardar el ensayo de cilindro: " + error.message);
  }
});

$("#slip-schedule-form")?.addEventListener("change", (event) => {
  if (event.target?.name?.startsWith("resultado_")) {
    updateCylinderResultControls(event.currentTarget);
  }
});

$("#program-pass-4h-btn")?.addEventListener("click", () => saveSimpleCylinderEvaluation("PASA"));
$("#program-fail-4h-btn")?.addEventListener("click", () => saveSimpleCylinderEvaluation("FALLA"));
$("#program-pass-5h-btn")?.addEventListener("click", () => saveSimpleCylinderEvaluation("FALLA", "PASA"));
$("#program-fail-5h-btn")?.addEventListener("click", () => saveSimpleCylinderEvaluation("FALLA", "FALLA"));
$("#program-pass-6h-btn")?.addEventListener("click", () => saveSimpleCylinderEvaluation("FALLA", "FALLA", "PASA"));
$("#program-fail-6h-btn")?.addEventListener("click", () => saveSimpleCylinderEvaluation("FALLA", "FALLA", "FALLA"));
$("#program-go-capture-btn")?.addEventListener("click", () => activateTab("captura"));
$("#program-next-evaluation-btn")?.addEventListener("click", goToNextCylinderEvaluation);
$("#program-correct-result-btn")?.addEventListener("click", prepareCylinderCorrection);
$("#program-change-zone-btn")?.addEventListener("click", async () => {
  const current = String(selectedCylinderEvaluationZone(state.schedule || {}, $("#slip-schedule-form")));
  const value = await appPrompt("Indica la zona/capa que quieres evaluar.", current, {
    title: "Cambiar zona",
    promptLabel: "Zona",
    confirmText: "Usar zona",
  });
  if (value === null) return;
  const zone = Number(value);
  if (!Number.isFinite(zone) || zone < 1) return alert("Captura una zona valida.");
  state.programSimpleZoneOverride = String(Math.trunc(zone));
  renderSlipSchedule(state.schedule || {});
});

$("#program-apply-recipe-btn")?.addEventListener("click", async () => {
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  const suggestion = state.schedule?.estado_ensayo?.receta_sugerida || programaToSuggestion(state.schedule?.programa);
  if (!suggestion) return alert("No hay receta sugerida por cilindro.");
  const active = activeAdvanceRecipe();
  const ok = await appConfirm(
    [
      "El ensayo de cilindro recomienda ajustar la receta.",
      "",
      `Actual: ${format(active.avance_objetivo_cm, 1)} cm cada ${format(active.intervalo_objetivo_min, 1)} min.`,
      `Sugerida: ${recipeSuggestionText(suggestion)}.`,
    ].join("\n"),
    { title: "Aplicar receta de cilindro", type: "warning", confirmText: "Aplicar receta" }
  );
  if (!ok) return;
  try {
    const applied = await api("/api/programa-deslizado/aplicar-receta", {
      method: "POST",
      body: JSON.stringify({
        colado_id: state.activeColadoId,
        fecha_hora: formatDatetimeLocal(new Date()),
        operador: activeColado()?.operador || "",
      }),
    });
    if (applied?.receta_activa) {
      state.moldState = { ...(state.moldState || {}), receta_avance: applied.receta_activa };
      renderOperatorTab(state.moldState);
    }
    await refreshMoldState();
    await refreshScadaState();
    await refreshSlipSchedule();
    await refreshOperatorTrendsSilently();
    showAppNotice("Receta de cilindro aplicada.", "success");
  } catch (error) {
    alert("No se pudo aplicar la receta de cilindro: " + error.message);
  }
});

$("#use-recipe-suggestion-btn")?.addEventListener("click", () => {
  const suggestion = state.moldState?.prediccion_deslizamiento?.receta_sugerida;
  if (!suggestion) return alert("No hay una receta sugerida aplicable.");
  fillAdvanceRecipeFormFromSuggestion(suggestion);
  showAppNotice("Sugerencia cargada en el formulario. Revisa y presiona Guardar Receta.", "info");
});

$("#advance-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (isColadoClosed()) return alert("El colado esta finalizado. Reabre el colado antes de registrar avances.");
  await registerAdvance(Object.fromEntries(new FormData(event.target).entries()));
});

$("#advance-5min-btn")?.addEventListener("click", async () => {
  if (isColadoClosed()) return alert("El colado esta finalizado. Solo quedan disponibles consulta, reportes, respaldo y evidencia.");
  const status = state.moldState?.estado_operativo || "SIN_ZONAS";
  if (status === "SIN_ZONAS" || status === "MOLDE_INCOMPLETO") {
    activateTab("captura");
    updateTruckZoneFormDefaults(true);
    $("#truck-zone-form input[name='hora_salida_planta']")?.focus();
    return;
  }
  if (!latestInspectionOk()) {
    alert("Primero confirma la inspeccion en el checklist rapido. El boton principal queda reservado para registrar el deslizado.");
    $("#check-no-desmorona")?.focus();
    return;
  }
  if (status === "PREPARARSE") {
    alert("El sistema esta en PREPARARSE. Confirma condiciones fisicas y espera estado liberable antes de registrar deslizado.");
    return;
  }
  const recipe = activeAdvanceRecipe();
  await confirmScadaDecision({
    decision_operador: "AVANZAR",
    avance_cm: recipe.avance_objetivo_cm,
    intervalo_minutos: recipe.intervalo_objetivo_min,
    origen: "manual",
    step_minutes: recipe.intervalo_objetivo_min,
    registrar_avance: true,
    checklist: quickChecklistPayload(),
  });
});

$("#confirm-inspection-btn")?.addEventListener("click", async () => {
  await confirmInspectionFromChecklist();
});

$("#confirm-checklist-btn")?.addEventListener("click", confirmInspectionFromChecklist);

$("#pause-btn")?.addEventListener("click", async () => {
  if (isColadoClosed()) return alert("El colado esta finalizado.");
  await confirmScadaDecision({ decision_operador: "PAUSAR", registrar_avance: false });
});

$("#resume-btn")?.addEventListener("click", async () => {
  if (isColadoClosed()) return alert("El colado esta finalizado.");
  await confirmScadaDecision({ decision_operador: "REANUDAR", registrar_avance: false });
});

$("#simulate-btn")?.addEventListener("click", async () => {
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  const curveId = $("#curva-select").value || activeColado()?.curva_id || "";
  if (!curveId) return alert("Selecciona una curva de referencia para simular.");
  const replaceExisting = await appConfirm("La simulacion puede reemplazar lecturas existentes del colado. Si cancelas, se agregara al historial.", {
    title: "Simular curva",
    confirmText: "Reemplazar",
    cancelText: "Agregar",
  });
  try {
    const result = await api("/api/simular-curva", {
      method: "POST",
      body: JSON.stringify({
        colado_id: state.activeColadoId,
        curva_id: curveId,
        interval_minutes: 5,
        replace_existing: replaceExisting,
      }),
    });
    alert(`Lecturas simuladas: ${result.lecturas_importadas}`);
    await refreshPrediction();
    await refreshMoldState();
  } catch (error) {
    alert("No se pudo simular: " + error.message);
  }
});

$("#simulate-operation-btn")?.addEventListener("click", async () => {
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  const recipe = activeAdvanceRecipe();
  const stepsRaw = await appPrompt("Define cuantos avances quieres simular.", "12", {
    title: "Simular operacion",
    promptLabel: "Avances",
    confirmText: "Simular",
  });
  const steps = Number(stepsRaw || 0);
  if (!Number.isFinite(steps) || steps <= 0) return;
  const replaceExisting = await appConfirm("Aceptar para reemplazar avances existentes. Cancelar para agregarlos al historial.", {
    title: "Historial de avances",
    confirmText: "Reemplazar",
    cancelText: "Agregar",
  });
  const startTime = state.evaluationTime || formatDatetimeLocal(new Date());
  try {
    const result = await api("/api/simular-operacion", {
      method: "POST",
      body: JSON.stringify({
        colado_id: state.activeColadoId,
        fecha_hora_inicio: startTime,
        pasos: steps,
        replace_existing: replaceExisting,
        operador: activeColado()?.operador || "Simulador",
      }),
    });
    alert(
      `Avances simulados: ${result.avances_generados}. Receta: ${format(recipe.avance_objetivo_cm, 1)} cm cada ${format(
        recipe.intervalo_objetivo_min,
        1
      )} min.`
    );
    await refreshPrediction();
    await refreshMoldState();
    await refreshScadaState();
    await refreshTrends();
  } catch (error) {
    alert("No se pudo simular la operacion: " + error.message);
  }
});

$("#sync-btn")?.addEventListener("click", syncOffline);

$("#trend-zone-select")?.addEventListener("change", refreshTrends);
$("#trend-range-select")?.addEventListener("change", refreshTrends);
$("#mini-trend-chart")?.addEventListener("click", () => activateTab("reportes"));
document.querySelectorAll(".scada-detail").forEach((detail) => {
  detail.addEventListener("toggle", () => setTimeout(() => window.SlipformECharts?.resizeAll(), 50));
});

$("#create-demo-btn")?.addEventListener("click", async () => {
  const result = await createTrainingColado();
  if (result) alert("Demo creada. Registra ollas desde Captura para practicar.");
});

$("#create-full-demo-btn")?.addEventListener("click", async () => {
  const created = await createTrainingColado();
  if (!created) return;
  const coladoId = state.activeColadoId;
  const colado = activeColado();
  const start = new Date();
  start.setHours(start.getHours() - 4);
  const startValue = formatDatetimeLocal(start);
  try {
    await api("/api/zonas/generar", {
      method: "POST",
      body: JSON.stringify({
        colado_id: coladoId,
        hora_zona_1: startValue,
        intervalo_minutos: 60,
        temperatura_inicial_c: 27.5,
        mezcla_id: colado?.mezcla_id || "",
        curva_id: colado?.curva_id || "",
      }),
    });
    if (colado?.curva_id) {
      await api("/api/simular-curva", {
        method: "POST",
        body: JSON.stringify({
          colado_id: coladoId,
          curva_id: colado.curva_id,
          interval_minutes: 5,
          replace_existing: true,
        }),
      });
    }
    await api("/api/simular-operacion", {
      method: "POST",
      body: JSON.stringify({
        colado_id: coladoId,
        fecha_hora_inicio: formatDatetimeLocal(new Date()),
        pasos: 12,
        replace_existing: true,
        operador: colado?.operador || "Entrenamiento",
      }),
    });
    setEvaluationTime("");
    await refreshPrediction();
    await refreshMoldState();
    await refreshScadaState();
    await refreshTrends();
    await refreshOperationalData();
    activateTab("operador");
    alert("Demo completa lista: zonas, temperaturas y avances simulados cargados.");
  } catch (error) {
    alert("No se pudo completar la demo: " + error.message);
  }
});

async function createTrainingColado() {
  const mezclas = state.bootstrap.mezclas || [];
  if (!mezclas.length) {
    alert("Primero importa curvas/mezclas de laboratorio.");
    return null;
  }
  const mezcla = mezclas[0];
  const curva = (state.bootstrap.curvas || []).find((c) => Number(c.mezcla_id) === Number(mezcla.id));
  const now = new Date();
  const start = formatDatetimeLocal(now);
  try {
    const result = await api("/api/colados", {
      method: "POST",
      body: JSON.stringify({
        silo_id: "DEMO",
        mezcla_id: mezcla.id,
        curva_id: curva?.id || "",
        fecha_hora_inicio: start,
        operador: "Entrenamiento",
        es_demo: true,
        observaciones: "Colado demo para practica operativa.",
      }),
    });
    state.activeColadoId = String(result.id);
    localStorage.setItem("activeColadoId", state.activeColadoId);
    await loadBootstrap();
    return result;
  } catch (error) {
    alert("No se pudo crear demo: " + error.message);
    return null;
  }
}

$("#quick-reading-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  await saveReadingFromForm(event.target, true);
});

document.querySelectorAll(".quick-event-btn").forEach((button) => {
  button.addEventListener("click", async () => {
    setQuickChecklistForResult(button.dataset.result);
    await registerQuickEvent(button.dataset.result);
  });
});

document.querySelectorAll("#operator-slide-form input[name='resultado_fisico']").forEach((input) => {
  input.addEventListener("change", () => setOperatorChecklistForResult(input.value));
});

$("#operator-action-btn")?.addEventListener("click", handleOperatorAction);
$("#operator-authorize-btn")?.addEventListener("click", handleOperatorAuthorization);
$("#operator-zone-temp-btn")?.addEventListener("click", () => {
  const zoneId = $("#operator-zone-temp-btn")?.dataset.zoneId || state.moldState?.zona_en_liberacion?.id || "";
  saveOperatorZoneTemperature(zoneId);
});
startOperatorLoop();

["#check-no-desmorona", "#check-no-se-pega", "#check-acabado", "#check-sin-arrastre"].forEach((selector) => {
  $(selector)?.addEventListener("change", renderOperationalGuidance);
});

$("#project-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.target).entries());
  try {
    await api("/api/proyecto", { method: "POST", body: JSON.stringify(payload) });
    await loadBootstrap();
    alert("Datos del proyecto guardados.");
  } catch (error) {
    alert("No se pudo guardar el proyecto: " + error.message);
  }
});

$("#turno-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  const payload = Object.fromEntries(new FormData(event.target).entries());
  payload.colado_id = state.activeColadoId;
  payload.inicio_turno = payload.inicio_turno || state.evaluationTime || formatDatetimeLocal(new Date());
  try {
    await api("/api/turnos", { method: "POST", body: JSON.stringify(payload) });
    event.target.reset();
    await refreshOperationalData();
    alert("Turno guardado.");
  } catch (error) {
    alert("No se pudo guardar el turno: " + error.message);
  }
});

$("#foto-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  const form = event.target;
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.colado_id = state.activeColadoId;
  payload.fecha_hora = payload.fecha_hora || state.evaluationTime || formatDatetimeLocal(new Date());
  const file = form.elements.imagen.files[0];
  if (file) payload.imagen_data_url = await fileToDataUrl(file);
  delete payload.imagen;
  try {
    await api("/api/fotografias", { method: "POST", body: JSON.stringify(payload) });
    form.reset();
    await refreshOperationalData();
    alert("Fotografia guardada.");
  } catch (error) {
    alert("No se pudo guardar la fotografia: " + error.message);
  }
});

$("#report-photo-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  const form = event.target;
  const files = [...(form.elements.imagenes?.files || [])];
  if (!files.length) return alert("Selecciona una o mas imagenes.");
  const data = Object.fromEntries(new FormData(form).entries());
  const status = $("#report-photo-status");
  const baseDescription = String(data.descripcion || "").trim();
  const fecha = data.fecha_hora || state.evaluationTime || formatDatetimeLocal(new Date());
  try {
    if (status) status.textContent = `Cargando ${files.length} imagen(es)...`;
    for (const [index, file] of files.entries()) {
      const payload = {
        colado_id: state.activeColadoId,
        fecha_hora: fecha,
        operador: data.operador || activeColado()?.operador || "",
        descripcion: baseDescription || file.name || `Imagen ${index + 1}`,
        imagen_data_url: await fileToDataUrl(file),
      };
      if (files.length > 1 && baseDescription) payload.descripcion = `${baseDescription} ${index + 1}`;
      await api("/api/fotografias", { method: "POST", body: JSON.stringify(payload) });
    }
    form.reset();
    await refreshOperationalData();
    if (status) status.textContent = `${files.length} imagen(es) cargada(s).`;
    alert("Imagenes cargadas al reporte.");
  } catch (error) {
    if (status) status.textContent = "";
    alert("No se pudieron cargar las imagenes: " + error.message);
  }
});

$("#desplome-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  const payload = Object.fromEntries(new FormData(event.target).entries());
  payload.colado_id = state.activeColadoId;
  payload.fecha_hora = state.evaluationTime || formatDatetimeLocal(new Date());
  try {
    await api("/api/desplomes", { method: "POST", body: JSON.stringify(payload) });
    event.target.reset();
    await refreshOperationalData();
    alert("Desplome guardado.");
  } catch (error) {
    alert("No se pudo guardar el desplome: " + error.message);
  }
});

$("#refresh-sensor-health-btn")?.addEventListener("click", refreshOperationalData);
$("#refresh-diagnostics-btn")?.addEventListener("click", refreshDiagnostics);
$("#diagnostics-sync-btn")?.addEventListener("click", syncOffline);
$("#create-backup-btn")?.addEventListener("click", async () => {
  try {
    await api("/api/backups", { method: "POST", body: JSON.stringify({ motivo: "manual_ui" }) });
    await refreshDiagnostics();
    alert("Backup creado.");
  } catch (error) {
    alert("No se pudo crear el backup: " + error.message);
  }
});

$("#written-log-template-btn")?.addEventListener("click", async () => {
  try {
    const result = await api("/api/bitacora-escrita/plantillas", { method: "POST", body: JSON.stringify({}) });
    setWrittenLogStatus(`Plantillas listas en: ${result.directorio}`, "ok");
    renderWrittenLogPreview({
      resumen: {
        ollas_total: 0,
        ollas_importar: 0,
        eventos_total: 0,
        eventos_importar: 0,
        zonas_previas: 0,
        avances_importar: 0,
        avance_total_visible_estimado: 0,
        imagenes_evidencia: 0,
        advertencias: 0,
        errores: 0,
      },
      avisos: [`Ollas: ${result.ollas}`, `Eventos: ${result.eventos}`],
      puede_importar: false,
    });
  } catch (error) {
    setWrittenLogStatus("No se pudieron crear las plantillas: " + error.message, "error");
  }
});

$("#written-log-preview-btn")?.addEventListener("click", async () => {
  try {
    const payload = await writtenLogPayload();
    const result = await api("/api/bitacora-escrita/preview", { method: "POST", body: JSON.stringify(payload) });
    state.writtenLogPreview = result;
    renderWrittenLogPreview(result);
    $("#written-log-import-btn").disabled = !result.puede_importar;
    setWrittenLogStatus(result.puede_importar ? "Vista previa lista para importar." : "Corrige los errores antes de importar.", result.puede_importar ? "ok" : "error");
  } catch (error) {
    state.writtenLogPreview = null;
    $("#written-log-import-btn").disabled = true;
    setWrittenLogStatus("No se pudo generar la vista previa: " + error.message, "error");
  }
});

$("#written-log-auto-btn")?.addEventListener("click", async () => {
  try {
    if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
    setWrittenLogStatus("Analizando imagenes con OCR experimental...", "", "#written-log-ocr-status");
    const result = await api("/api/bitacora-escrita/ocr-preview", {
      method: "POST",
      body: JSON.stringify(writtenLogBasePayload()),
    });
    state.writtenLogAutoCsv = result.csv || null;
    state.writtenLogPreview = result.preview;
    renderWrittenLogPreview(result.preview || {});
    renderWrittenLogOcrStatus(result);
    $("#written-log-import-btn").disabled = !result.preview?.puede_importar;
    setWrittenLogStatus(
      result.preview?.puede_importar ? "Candidatos OCR listos para importar." : "OCR revisado: no hay candidatos importables sin correccion.",
      result.preview?.puede_importar ? "ok" : "error"
    );
  } catch (error) {
    state.writtenLogAutoCsv = null;
    $("#written-log-import-btn").disabled = true;
    setWrittenLogStatus("No se pudo ejecutar OCR: " + error.message, "error", "#written-log-ocr-status");
  }
});

$("#written-log-import-btn")?.addEventListener("click", async () => {
  try {
    const payload = await writtenLogPayload();
    const preview = state.writtenLogPreview;
    if (!preview?.puede_importar) return alert("Primero genera una vista previa sin errores.");
    const summary = preview.resumen || {};
    const ok = await appConfirm(
      `Se creara un backup SQLite antes de importar. Ollas: ${summary.ollas_importar || 0}. Eventos: ${summary.eventos_importar || 0}. Eventos a reemplazar: ${summary.eventos_reemplazar || 0}. Avances: ${summary.avances_importar || 0}. Total visible estimado: ${format(summary.avance_total_visible_estimado || 0, 1)} cm. Imagenes: ${summary.imagenes_evidencia || 0}.`,
      { title: "Confirmar importacion", confirmText: "Importar bitacora" }
    );
    if (!ok) return;
    const result = await api("/api/bitacora-escrita/importar", { method: "POST", body: JSON.stringify(payload) });
    state.writtenLogPreview = result.preview;
    renderWrittenLogPreview(result.preview || result);
    setWrittenLogStatus(`Importacion completada. Backup: ${result.backup?.path || result.backup?.archivo || "creado"}`, "ok");
    $("#written-log-import-btn").disabled = true;
    await loadBootstrap();
  } catch (error) {
    setWrittenLogStatus("No se pudo importar la bitacora: " + error.message, "error");
  }
});

[
  "#written-log-ollas-file",
  "#written-log-events-file",
  "#written-log-first-fresh-zone",
  "#written-log-create-advances",
  "#written-log-existing-advances-mode",
  "#written-log-advance-interpretation",
  "#written-log-events-mode",
].forEach((selector) => {
  $(selector)?.addEventListener("change", () => {
    if (selector.includes("file")) state.writtenLogAutoCsv = null;
    $("#written-log-import-btn").disabled = true;
    setWrittenLogStatus("Configuracion de importacion actualizada. Genera vista previa antes de importar.");
  });
});

function writtenLogBasePayload() {
  return {
    colado_id: state.activeColadoId,
    fecha_base: $("#written-log-base-date")?.value || "2026-08-04",
    modo_existentes: $("#written-log-mode")?.value || "omitir",
    primera_zona_fresca: $("#written-log-first-fresh-zone")?.value || "1",
    crear_avances_desde_eventos: Boolean($("#written-log-create-advances")?.checked),
    interpretacion_avance_deslizado: $("#written-log-advance-interpretation")?.value || "acumulado_desde_inicio",
    modo_avances_existentes: $("#written-log-existing-advances-mode")?.value || "bloquear",
    modo_eventos_importados: $("#written-log-events-mode")?.value || "bloquear",
    operador: $("#written-log-operator")?.value || activeColado()?.operador || "",
  };
}

async function writtenLogPayload() {
  if (!state.activeColadoId) throw new Error("Selecciona o crea un colado.");
  const ollasInput = $("#written-log-ollas-file");
  const eventsInput = $("#written-log-events-file");
  const autoCsv = state.writtenLogAutoCsv || {};
  const ollasFile = ollasInput?.files?.[0];
  const eventsFile = eventsInput?.files?.[0];
  return {
    ...writtenLogBasePayload(),
    ollas_csv: ollasFile ? await readTextFile(ollasFile) : autoCsv.ollas || "",
    eventos_csv: eventsFile ? await readTextFile(eventsFile) : autoCsv.eventos || "",
  };
}

function readTextFile(file) {
  if (!file) return Promise.resolve("");
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error(`No se pudo leer ${file.name}.`));
    reader.readAsText(file, "utf-8");
  });
}

function setWrittenLogStatus(message, type = "", selector = "#written-log-status") {
  const status = $(selector);
  if (!status) return;
  status.textContent = message;
  status.classList.toggle("ok", type === "ok");
  status.classList.toggle("error", type === "error");
}

function renderWrittenLogPreview(result = {}) {
  const target = $("#written-log-preview");
  if (!target) return;
  const summary = result.resumen || {};
  const messages = [...(result.avisos || []), ...writtenLogMessages(result)];
  target.innerHTML = `
    <div class="written-log-summary">
      <div><span>Ollas CSV</span><strong>${summary.ollas_total || 0}</strong></div>
      <div><span>Ollas a guardar</span><strong>${summary.ollas_importar || 0}</strong></div>
      <div><span>Eventos</span><strong>${summary.eventos_importar || 0}</strong></div>
      <div><span>Eventos existentes</span><strong>${summary.eventos_importados_existentes || 0}</strong></div>
      <div><span>Zonas previas</span><strong>${summary.zonas_previas || 0}</strong></div>
      <div><span>Avances</span><strong>${summary.avances_importar || 0}</strong></div>
      <div><span>Total visible</span><strong>${format(summary.avance_total_visible_estimado || 0, 1)} cm</strong></div>
      <div><span>Imagenes</span><strong>${summary.imagenes_evidencia || 0}</strong></div>
      <div><span>Alertas</span><strong>${(summary.errores || 0) + (summary.advertencias || 0)}</strong></div>
    </div>
    ${
      messages.length
        ? `<ul class="written-log-message-list">${messages.slice(0, 12).map((item) => `<li class="${item.type || ""}">${escapeHtml(item.text || item)}</li>`).join("")}</ul>`
        : `<p class="hint">Sin errores ni advertencias en la vista previa.</p>`
    }
  `;
}

function writtenLogMessages(result = {}) {
  const errors = [];
  const warnings = [];
  const collect = (prefix, rows) => {
    (rows || []).forEach((row) => {
      (row.errores || []).forEach((text) => errors.push({ type: "error", text: `${prefix} linea ${row.linea}: ${text}` }));
      (row.advertencias || []).forEach((text) => warnings.push({ type: "warning", text: `${prefix} linea ${row.linea}: ${text}` }));
    });
  };
  collect("Ollas", result.ollas?.filas);
  collect("Eventos", result.eventos?.filas);
  collect("Avances", result.avances_deslizamiento?.filas);
  (result.eventos?.errores || []).forEach((text) => errors.push({ type: "error", text: `Eventos: ${text}` }));
  (result.eventos?.advertencias || []).forEach((text) => warnings.push({ type: "warning", text: `Eventos: ${text}` }));
  (result.arranque_historico?.errores || []).forEach((text) => errors.push({ type: "error", text: `Arranque historico: ${text}` }));
  (result.arranque_historico?.advertencias || []).forEach((text) => warnings.push({ type: "warning", text: `Arranque historico: ${text}` }));
  (result.avances_deslizamiento?.errores || []).forEach((text) => errors.push({ type: "error", text: `Avances: ${text}` }));
  (result.avances_deslizamiento?.advertencias || []).forEach((text) => warnings.push({ type: "warning", text: `Avances: ${text}` }));
  return [...errors, ...warnings];
}

function renderWrittenLogOcrStatus(result = {}) {
  const images = result.imagenes || [];
  const preview = result.preview?.resumen || {};
  const detail = [
    result.mensaje || "OCR sin mensaje.",
    `Imagenes detectadas: ${images.length}.`,
    `Ollas candidatas: ${preview.ollas_total || 0}. Eventos candidatos: ${preview.eventos_total || 0}.`,
  ].join(" ");
  setWrittenLogStatus(detail, result.motor_disponible ? "ok" : "error", "#written-log-ocr-status");
}

async function resetDemoDataFromUi(source = "diagnostico") {
  if (
    !(await appConfirm("Esto eliminara solo colados demo y creara un backup previo. Los datos reales no se borran.", {
      title: "Limpiar datos demo",
      type: "danger",
      confirmText: "Limpiar demo",
    }))
  ) return;
  try {
    const colado = activeColado();
    await api("/api/demo/reset", {
      method: "POST",
      body: JSON.stringify({ operador: colado?.operador || "", motivo: `reset demo desde ${source}` }),
    });
    if (activeColado()?.es_demo) clearActiveColado();
    await loadBootstrap();
    alert("Datos demo eliminados.");
  } catch (error) {
    alert("No se pudieron limpiar los datos demo: " + error.message);
  }
}

$("#reset-demo-btn")?.addEventListener("click", () => resetDemoDataFromUi("diagnostico"));
$("#home-reset-demo-btn")?.addEventListener("click", () => resetDemoDataFromUi("inicio"));

$("#model-adjustment-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  const payload = Object.fromEntries(new FormData(event.target).entries());
  payload.colado_id = state.activeColadoId;
  payload.fecha_hora = state.evaluationTime || formatDatetimeLocal(new Date());
  try {
    await api("/api/modelo/ajustes", { method: "POST", body: JSON.stringify(payload) });
    event.target.reset();
    await refreshOperationalData();
    alert("Ajuste registrado.");
  } catch (error) {
    alert("No se pudo guardar el ajuste: " + error.message);
  }
});

function activeColado() {
  return (state.bootstrap.colados || []).find((c) => String(c.id) === String(state.activeColadoId));
}

function coladoFormPayload() {
  const data = Object.fromEntries(new FormData($("#colado-form")).entries());
  return {
    silo_id: data.silo_id,
    mezcla_id: data.mezcla_id,
    curva_id: data.curva_id,
    operador: data.operador,
    estado: data.estado || "ACTIVO",
    fecha_cierre: data.fecha_cierre || "",
    es_demo: data.es_demo === "on",
    observaciones: data.observaciones,
  };
}

async function saveReadingFromForm(form, resetAfter = false) {
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  if (isColadoClosed()) return alert("El colado esta finalizado. Reabre el colado antes de registrar lecturas.");
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.colado_id = state.activeColadoId;
  payload.fecha_hora = state.evaluationTime || formatDatetimeLocal(new Date());
  payload.minuto_transcurrido = payload.minuto_transcurrido || autoMinute(payload.fecha_hora) || "";
  payload.origen = payload.origen || "manual";
  try {
    await api("/api/lecturas", { method: "POST", body: JSON.stringify(payload) });
    rememberLocalReading(payload);
    if (resetAfter) form.reset();
    await refreshPrediction();
    await refreshMoldState();
    await refreshScadaState();
    await refreshTrends();
  } catch (error) {
    queueOffline("/api/lecturas", payload);
    rememberLocalReading(payload);
    if (resetAfter) form.reset();
  }
}

async function saveOperatorTemperature(reading, fechaHora) {
  if (isColadoClosed()) return;
  const data = typeof reading === "object" ? reading : { temperatura_concreto_c: reading };
  const payload = {
    colado_id: state.activeColadoId,
    fecha_hora: fechaHora,
    minuto_transcurrido: autoMinute(fechaHora) || "",
    temperatura_concreto_c: data.temperatura_concreto_c,
    temperatura_ambiente_c: data.temperatura_ambiente_c || "",
    humedad_relativa_pct: data.humedad_relativa_pct || "",
    origen: "manual",
  };
  try {
    await api("/api/lecturas", { method: "POST", body: JSON.stringify(payload) });
    rememberLocalReading(payload);
  } catch (error) {
    queueOffline("/api/lecturas", payload);
    rememberLocalReading(payload);
    showAppNotice("Sin conexion: temperatura pendiente de sincronizar.", "error");
  }
}

function operatorChecklistFromForm(form) {
  return {
    inspeccion_fisica: true,
    no_desmorona: Boolean(form.elements.no_desmorona.checked),
    no_se_pega: Boolean(form.elements.no_se_pega.checked),
    acabado_aceptable: Boolean(form.elements.acabado_aceptable.checked),
    sin_arrastre: Boolean(form.elements.sin_arrastre.checked),
  };
}

function setOperatorChecklistForResult(result) {
  const form = $("#operator-slide-form");
  if (!form) return;
  form.elements.no_desmorona.checked = result !== "desmorona";
  form.elements.no_se_pega.checked = result !== "se_pega";
  form.elements.acabado_aceptable.checked = !["desmorona", "fisura"].includes(result);
  form.elements.sin_arrastre.checked = result !== "arrastra";
}

function openOperatorDialog(action) {
  const backdrop = $("#operator-dialog");
  const form = $("#operator-slide-form");
  if (!backdrop || !form) return Promise.resolve(null);
  const title = $("#operator-dialog-title");
  const message = $("#operator-dialog-message");
  const confirm = $("#operator-dialog-confirm");
  const cancel = $("#operator-dialog-cancel");
  const dialog = backdrop.querySelector(".operator-dialog");
  const supervisorRow = $("#operator-supervisor-row");
  const supervisorInput = $("#operator-supervisor-input");
  const observationInput = form.elements.observacion;
  const latest = latestTemperatureReading();
  const zoneTemp = state.moldState?.zona_en_liberacion?.temperatura_actual_c;
  const isAuthorization = action === "authorize-early-slide";
  form.reset();
  form.elements.temperatura_concreto_c.value = latest?.temperatura_concreto_c ?? zoneTemp ?? "";
  form.elements.temperatura_ambiente_c.value = latest?.temperatura_ambiente_c ?? "";
  form.elements.humedad_relativa_pct.value = latest?.humedad_relativa_pct ?? "";
  dialog?.classList.toggle("authorization", isAuthorization);
  if (supervisorRow) supervisorRow.hidden = !isAuthorization;
  if (supervisorInput) {
    supervisorInput.required = isAuthorization;
    supervisorInput.value = "";
  }
  if (observationInput) {
    observationInput.required = isAuthorization;
    observationInput.placeholder = isAuthorization ? "Motivo obligatorio de la autorizacion" : "Opcional";
  }
  title.textContent = isAuthorization
    ? "Marcar lista por inspeccion"
    : action === "review"
      ? "Revisar concreto"
      : action === "slide-risk"
        ? "Deslizar con vigilancia"
        : "Confirmar deslizado";
  message.textContent = isAuthorization
    ? "La zona no alcanzo la madurez minima calculada. Se guardara con madurez operativa 90% por criterio de campo y luego podras deslizar con la receta activa."
    : action === "review"
      ? "Captura temperatura e inspeccion. No se registrara avance."
      : "Captura temperatura e inspeccion antes de registrar el deslizado.";
  confirm.textContent = isAuthorization ? "Marcar lista" : action === "review" ? "Guardar revision" : "Confirmar deslizado";
  backdrop.hidden = false;
  document.body.classList.add("app-dialog-open");
  setTimeout(() => form.elements.temperatura_concreto_c.focus(), 0);
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      backdrop.hidden = true;
      document.body.classList.remove("app-dialog-open");
      form.removeEventListener("submit", onSubmit);
      cancel.removeEventListener("click", onCancel);
      backdrop.removeEventListener("click", onBackdrop);
      document.removeEventListener("keydown", onKeydown);
      dialog?.classList.remove("authorization");
      if (supervisorInput) supervisorInput.required = false;
      if (observationInput) observationInput.required = false;
      resolve(value);
    };
    const onSubmit = (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const result = form.elements.resultado_fisico.value;
      const checklist = operatorChecklistFromForm(form);
      finish({
        temperatura_concreto_c: Number(form.elements.temperatura_concreto_c.value),
        temperatura_ambiente_c: form.elements.temperatura_ambiente_c.value === "" ? "" : Number(form.elements.temperatura_ambiente_c.value),
        humedad_relativa_pct: form.elements.humedad_relativa_pct.value === "" ? "" : Number(form.elements.humedad_relativa_pct.value),
        resultado_fisico: result,
        observacion: form.elements.observacion.value,
        supervisor: form.elements.supervisor?.value || "",
        checklist,
      });
    };
    const onCancel = () => finish(null);
    const onBackdrop = (event) => {
      if (event.target === backdrop) onCancel();
    };
    const onKeydown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
      }
    };
    form.addEventListener("submit", onSubmit);
    cancel.addEventListener("click", onCancel);
    backdrop.addEventListener("click", onBackdrop);
    document.addEventListener("keydown", onKeydown);
  });
}

function operatorZoneById(zoneId) {
  const zones = state.moldState?.zonas_activas || [];
  return zones.find((zone) => String(zone.id) === String(zoneId || "")) || null;
}

function operatorZoneSummary(zone) {
  if (!zone) return "Zona: --";
  return [
    `Zona ${zone.zona_numero}`,
    `${format(zone.elevacion_inferior_cm, 0)}-${format(zone.elevacion_superior_cm, 0)} cm`,
    zone.numero_olla ? `Olla ${zone.numero_olla}` : zone.es_zona_heredada ? "Existente previo" : "",
    zone.hora_salida_planta ? `Salida ${formatZoneTime(zone.hora_salida_planta)}` : "",
  ]
    .filter(Boolean)
    .join(" | ");
}

async function confirmZoneTemperaturePayload(payload, zone) {
  const warnings = [];
  const readingTime = parseLocalDateTime(payload.fecha_hora);
  const futureLimit = new Date(Date.now() + 15 * 60000);
  if (readingTime && readingTime > futureLimit) {
    warnings.push(`La hora de lectura esta en el futuro: ${formatZoneTime(payload.fecha_hora)}.`);
  }
  const concrete = Number(payload.temperatura_concreto_c);
  if (Number.isFinite(concrete) && (concrete < 5 || concrete > 60)) {
    warnings.push(`Temperatura de concreto inusual para ${operatorZoneSummary(zone)}: ${format(concrete, 1)} C.`);
  }
  if (!warnings.length) return true;
  const ok = await appConfirm(
    [
      ...warnings.map((text) => `- ${text}`),
      "",
      "Esta lectura afectara la madurez calculada de la zona seleccionada.",
    ].join("\n"),
    {
      title: "Confirmar lectura de zona",
      type: "warning",
      confirmText: "Guardar lectura",
      cancelText: "Corregir",
    }
  );
  if (!ok) showAppNotice("Corrige la lectura antes de guardarla.", "error");
  return ok;
}

async function refreshZoneTemperatureHistory(zone, target) {
  if (!target || !zone?.id) return;
  target.innerHTML = `<div class="zone-temperature-history-empty">Cargando lecturas...</div>`;
  try {
    const result = await api(`/api/lecturas-zona?zona_id=${encodeURIComponent(zone.id)}`);
    const readings = (result.lecturas || []).slice().reverse();
    if (!readings.length) {
      target.innerHTML = `<div class="zone-temperature-history-empty">Sin lecturas activas para esta zona.</div>`;
      return;
    }
    target.innerHTML = `<table class="zone-temperature-history-table">
      <thead><tr><th>Fecha</th><th>Concreto</th><th>Ambiente</th><th>HR</th><th></th></tr></thead>
      <tbody>${readings
        .map(
          (reading) => `<tr>
            <td>${escapeHtml(formatZoneTime(reading.fecha_hora))}</td>
            <td>${format(reading.temperatura_concreto_c, 1)} C</td>
            <td>${reading.temperatura_ambiente_c == null ? "--" : `${format(reading.temperatura_ambiente_c, 1)} C`}</td>
            <td>${reading.humedad_relativa_pct == null ? "--" : `${format(reading.humedad_relativa_pct, 1)}%`}</td>
            <td class="zone-temperature-history-actions">
              <button type="button" class="button-small secondary zone-temperature-correct" data-reading-id="${escapeHtml(reading.id)}">Corregir</button>
              <button type="button" class="button-small danger zone-temperature-invalidate" data-reading-id="${escapeHtml(reading.id)}">Anular</button>
            </td>
          </tr>`
        )
        .join("")}</tbody>
    </table>`;
    target.querySelectorAll(".zone-temperature-correct").forEach((button) => {
      button.addEventListener("click", () => {
        const reading = readings.find((item) => String(item.id) === String(button.dataset.readingId || ""));
        loadZoneTemperatureCorrection(reading, zone, target);
      });
    });
    target.querySelectorAll(".zone-temperature-invalidate").forEach((button) => {
      button.addEventListener("click", async () => {
        await invalidateZoneTemperatureReading(button.dataset.readingId, zone, target);
      });
    });
  } catch (error) {
    target.innerHTML = `<div class="zone-temperature-history-empty error">No se pudieron cargar las lecturas.</div>`;
  }
}

function loadZoneTemperatureCorrection(reading, zone, target) {
  const form = target?.closest("form");
  if (!reading || !form) return;
  form.dataset.correctReadingId = String(reading.id);
  form.elements.fecha_hora.value = toDatetimeLocalValue(reading.fecha_hora) || formatDatetimeLocal(new Date());
  form.elements.temperatura_concreto_c.value = reading.temperatura_concreto_c ?? "";
  form.elements.temperatura_ambiente_c.value = reading.temperatura_ambiente_c ?? "";
  form.elements.humedad_relativa_pct.value = reading.humedad_relativa_pct ?? "";
  const confirm = $("#zone-temperature-confirm");
  const warning = $("#zone-temperature-warning");
  if (confirm) confirm.textContent = "Guardar correccion";
  if (warning) {
    warning.hidden = false;
    warning.textContent = `Corrigiendo lectura de Zona ${zone.zona_numero}. Al guardar, la lectura anterior quedara anulada con auditoria.`;
  }
  form.elements.temperatura_concreto_c.focus();
}

async function invalidateZoneTemperatureReading(readingId, zone, target) {
  if (!readingId || !zone?.id) return;
  if (isColadoClosed()) {
    await appAlert("El colado esta finalizado. Reabre el colado antes de anular lecturas.", {
      title: "Colado finalizado",
      type: "warning",
    });
    return;
  }
  const reason = await appPrompt("Captura el motivo para anular esta lectura de temperatura.", "", {
    title: `Anular lectura Zona ${zone.zona_numero}`,
    promptLabel: "Motivo",
    confirmText: "Anular lectura",
    type: "danger",
  });
  const cleanReason = String(reason || "").trim();
  if (!cleanReason) {
    showAppNotice("La anulacion requiere motivo.", "error");
    return;
  }
  const ok = await appConfirm(
    `Se anulara la lectura seleccionada de Zona ${zone.zona_numero}. La madurez se recalculara usando solo lecturas validas.`,
    {
      title: "Confirmar anulacion",
      type: "danger",
      confirmText: "Anular",
      cancelText: "Cancelar",
    }
  );
  if (!ok) return;
  try {
    await api("/api/lecturas-zona/anular", {
      method: "POST",
      body: JSON.stringify({
        colado_id: state.activeColadoId,
        lectura_id: readingId,
        motivo: cleanReason,
        operador: activeColado()?.operador || "",
      }),
    });
    await refreshZoneTemperatureHistory(zone, target);
    await refreshPrediction();
    await refreshMoldState();
    await refreshScadaState();
    await refreshTrends();
    showAppNotice(`Lectura anulada para Zona ${zone.zona_numero}.`, "ok");
  } catch (error) {
    await appAlert("No se pudo anular la lectura: " + error.message, {
      title: "Error",
      type: "danger",
    });
  }
}

function openOperatorZoneTemperatureDialog(zoneId) {
  const backdrop = $("#zone-temperature-dialog");
  const form = $("#zone-temperature-form");
  if (!backdrop || !form) return Promise.resolve(null);
  const zone = operatorZoneById(zoneId);
  if (!zone?.id || zone.pendiente_olla) {
    appAlert("Selecciona una zona registrada antes de capturar temperatura.", {
      title: "Zona requerida",
      type: "warning",
    });
    return Promise.resolve(null);
  }
  const controlZone = state.moldState?.zona_en_liberacion || null;
  const isControlZone = controlZone?.id && String(controlZone.id) === String(zone.id);
  const title = $("#zone-temperature-dialog-title");
  const message = $("#zone-temperature-dialog-message");
  const summary = $("#zone-temperature-summary");
  const warning = $("#zone-temperature-warning");
  const history = $("#zone-temperature-history");
  const cancel = $("#zone-temperature-cancel");
  const dialog = backdrop.querySelector(".zone-temperature-dialog");
  form.reset();
  delete form.dataset.correctReadingId;
  form.elements.zona_colado_id.value = zone.id;
  form.elements.fecha_hora.value = formatDatetimeLocal(new Date());
  const confirm = $("#zone-temperature-confirm");
  if (confirm) confirm.textContent = "Guardar temperatura";
  if (title) title.textContent = `Temperatura Zona ${zone.zona_numero}`;
  if (message) message.textContent = "Guarda una lectura manual sin cambiar de pestana ni registrar avance.";
  if (summary) summary.textContent = operatorZoneSummary(zone);
  if (warning) {
    warning.hidden = isControlZone;
    warning.textContent = isControlZone
      ? ""
      : `Esta lectura se guardara para Zona ${zone.zona_numero}, no para la zona actualmente a liberar.`;
  }
  refreshZoneTemperatureHistory(zone, history);
  backdrop.hidden = false;
  document.body.classList.add("app-dialog-open");
  setTimeout(() => form.elements.temperatura_concreto_c.focus(), 0);

  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      backdrop.hidden = true;
      document.body.classList.remove("app-dialog-open");
      form.removeEventListener("submit", onSubmit);
      cancel.removeEventListener("click", onCancel);
      backdrop.removeEventListener("click", onBackdrop);
      document.removeEventListener("keydown", onKeydown);
      resolve(value);
    };
    const onSubmit = async (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const payload = Object.fromEntries(new FormData(form).entries());
      payload.colado_id = state.activeColadoId;
      payload.origen = "manual";
      if (!(await confirmZoneTemperaturePayload(payload, zone))) return;
      const correctionId = form.dataset.correctReadingId || "";
      finish({
        zone,
        payload,
        correction: correctionId
          ? {
              lectura_id: correctionId,
              motivo: `Correccion de lectura de temperatura de Zona ${zone.zona_numero}.`,
            }
          : null,
      });
    };
    const onCancel = () => finish(null);
    const onBackdrop = (event) => {
      if (event.target === backdrop) onCancel();
    };
    const onKeydown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
      }
    };
    form.addEventListener("submit", onSubmit);
    cancel.addEventListener("click", onCancel);
    backdrop.addEventListener("click", onBackdrop);
    document.addEventListener("keydown", onKeydown);
  });
}

async function saveOperatorZoneTemperature(zoneId) {
  if (!state.activeColadoId) {
    await appAlert("Selecciona o crea un colado antes de capturar temperatura.", {
      title: "Sin colado activo",
      type: "warning",
    });
    return;
  }
  if (isColadoClosed()) {
    await appAlert("El colado esta finalizado. Reabre el colado antes de capturar temperatura.", {
      title: "Colado finalizado",
      type: "warning",
    });
    return;
  }
  const result = await openOperatorZoneTemperatureDialog(zoneId);
  if (!result) return;
  try {
    const created = await api("/api/lecturas-zona", { method: "POST", body: JSON.stringify(result.payload) });
    if (result.correction?.lectura_id) {
      await api("/api/lecturas-zona/anular", {
        method: "POST",
        body: JSON.stringify({
          colado_id: state.activeColadoId,
          lectura_id: result.correction.lectura_id,
          motivo: `${result.correction.motivo} Reemplazada por lectura ${created.id}.`,
          operador: activeColado()?.operador || "",
        }),
      });
    }
    await refreshPrediction();
    await refreshMoldState();
    await refreshScadaState();
    await refreshTrends();
    showAppNotice(
      result.correction ? `Correccion guardada para Zona ${result.zone.zona_numero}.` : `Temperatura guardada para Zona ${result.zone.zona_numero}.`,
      "ok"
    );
  } catch (error) {
    if (error.status) {
      await appAlert("No se pudo guardar la temperatura de zona: " + error.message, {
        title: "Error",
        type: "danger",
      });
    } else {
      queueOffline("/api/lecturas-zona", result.payload);
      showAppNotice("Sin conexion: temperatura de zona pendiente de sincronizar.", "error");
    }
  }
}

window.openOperatorZoneTemperatureDialog = openOperatorZoneTemperatureDialog;
window.saveOperatorZoneTemperature = saveOperatorZoneTemperature;

async function handleOperatorAuthorization() {
  if (!canMarkReadyByFieldCriteria(state.moldState)) {
    await appAlert("Marcar lista por inspeccion solo aplica cuando la zona existe, el molde esta completo y la madurez calculada aun es menor al 90%.", {
      title: "Liberacion no aplicable",
      type: "warning",
    });
    return;
  }
  const timer = operatorTimerState();
  if (timer.timeIssue) {
    await appAlert("El ultimo avance tiene una hora futura. Corrige la hora antes de autorizar un deslizado.", {
      title: "Revisar hora",
      type: "danger",
    });
    return;
  }
  const modal = await openOperatorDialog("authorize-early-slide");
  if (!modal) return;
  const fechaHora = formatDatetimeLocal(new Date());
  await saveOperatorTemperature(
    {
      temperatura_concreto_c: modal.temperatura_concreto_c,
      temperatura_ambiente_c: modal.temperatura_ambiente_c,
      humedad_relativa_pct: modal.humedad_relativa_pct,
    },
    fechaHora
  );
  const allOk = checklistAllOk(modal.checklist);
  const conditionOk = modal.resultado_fisico === "correcto";
  const zone = state.moldState?.zona_en_liberacion;
  const observation = [
    "Flujo Operador: liberacion por criterio de campo.",
    `Zona: ${zone ? zone.zona_numero : "--"}.`,
    `Madurez calculada: ${zone ? format((zone.avance_madurez_calculada ?? zone.avance_madurez) * 100, 1) : "--"}%.`,
    "Madurez operativa: 90.0%.",
    `Condicion: ${modal.resultado_fisico}.`,
    `Motivo: ${modal.observacion || ""}`,
  ]
    .filter(Boolean)
    .join(" ");
  if (!allOk || !conditionOk) {
    await confirmScadaDecision({
      fecha_hora: fechaHora,
      decision_operador: "REVISION_CON_OBSERVACION",
      registrar_avance: false,
      checklist: modal.checklist,
      observacion: `${observation} No se registra avance por condicion fisica no conforme.`,
    });
    await appAlert("La condicion fisica o el checklist no permite autorizar el deslizado. Se guardo la revision sin avance.", {
      title: "No marcar lista",
      type: "danger",
    });
    return;
  }
  rememberLocalInspection(fechaHora, modal.checklist);
  updateInspectionSignal();
  const confirmed = await appConfirm(
    "Confirmas marcar esta zona como lista por criterio de campo? La madurez calculada se conservara y la madurez operativa quedara en 90%. Despues podras deslizar con la receta activa.",
    {
      title: "Confirmacion final",
      type: "danger",
      confirmText: "Si, marcar lista",
      cancelText: "Cancelar",
    }
  );
  if (!confirmed) return;
  try {
    await api("/api/zonas/liberar-por-criterio", {
      method: "POST",
      body: JSON.stringify({
        colado_id: state.activeColadoId,
        zona_colado_id: zone?.id,
        fecha_hora: fechaHora,
        temperatura_concreto_c: modal.temperatura_concreto_c,
        temperatura_ambiente_c: modal.temperatura_ambiente_c,
        humedad_relativa_pct: modal.humedad_relativa_pct,
        condicion_observada: modal.resultado_fisico,
        motivo: modal.observacion,
        operador: activeColado()?.operador || "",
        supervisor: modal.supervisor,
        checklist: modal.checklist,
      }),
    });
    await refreshPrediction();
    await refreshMoldState();
    await refreshScadaState();
    await refreshTrends();
    await appAlert("Zona marcada lista por criterio de campo. Ahora puedes registrar el deslizado con la receta activa.", {
      title: "Zona lista",
      type: "success",
    });
  } catch (error) {
    await appAlert("No se pudo marcar la zona como lista: " + error.message, {
      title: "Error",
      type: "danger",
    });
  }
}

async function handleOperatorAction() {
  if (isColadoClosed()) {
    await appAlert(`Este colado esta finalizado. ${coladoClosureText()}.`, {
      title: "Colado finalizado",
      type: "success",
    });
    return;
  }
  const button = $("#operator-action-btn");
  const action = button?.dataset.action || "capture";
  const status = state.moldState?.estado_operativo || "SIN_ZONAS";
  if (action === "capture") {
    activateTab("captura");
    $("#colado-select")?.focus();
    return;
  }
  if (action === "register-truck") {
    activateTab("captura");
    updateTruckZoneFormDefaults(true);
    $("#truck-zone-form input[name='hora_salida_planta']")?.focus();
    return;
  }
  if (action === "wait") {
    const timer = operatorTimerState();
    if (timer.timeIssue) {
      await appAlert("El ultimo avance guardado tiene una hora futura contra la hora real. Revisa la hora de evaluacion o limpia/repite la prueba antes de seguir.", {
        title: "Revisar hora",
        type: "warning",
      });
      return;
    }
    if (button?.classList.contains("timer-waiting") && !timer.ready) {
      await appAlert(`Aun faltan ${timer.label} para la siguiente evaluacion programada.`, {
        title: "Esperar temporizador",
        type: "warning",
      });
      return;
    }
    await appAlert("El sistema indica ESPERAR. No se registrara deslizado mientras la zona no sea liberable.", {
      title: "Esperar",
      type: "warning",
    });
    return;
  }
  const modal = await openOperatorDialog(action);
  if (!modal) return;
  const fechaHora = formatDatetimeLocal(new Date());
  const recipe = activeAdvanceRecipe();
  await saveOperatorTemperature({
    temperatura_concreto_c: modal.temperatura_concreto_c,
    temperatura_ambiente_c: modal.temperatura_ambiente_c,
    humedad_relativa_pct: modal.humedad_relativa_pct,
  }, fechaHora);
  const allOk = checklistAllOk(modal.checklist);
  const conditionOk = modal.resultado_fisico === "correcto";
  const observation = [
    `Flujo Operador. Condicion: ${modal.resultado_fisico}.`,
    modal.observacion || "",
  ].filter(Boolean).join(" ");
  if (allOk) {
    rememberLocalInspection(fechaHora, modal.checklist);
    updateInspectionSignal();
  }
  if (action === "review") {
    await confirmScadaDecision({
      fecha_hora: fechaHora,
      decision_operador: allOk ? "INSPECCION_OK" : "REVISION_CON_OBSERVACION",
      registrar_avance: false,
      checklist: modal.checklist,
      observacion: observation,
    });
    return;
  }
  if (!allOk || !conditionOk) {
    await confirmScadaDecision({
      fecha_hora: fechaHora,
      decision_operador: "REVISION_CON_OBSERVACION",
      registrar_avance: false,
      checklist: modal.checklist,
      observacion: `${observation} No se registra avance por condicion no conforme.`,
    });
    await appAlert("La condicion o checklist no permite deslizar. Se guardo la revision, pero no se registro avance.", {
      title: "No deslizar",
      type: "danger",
    });
    return;
  }
  if (["NO_LIBERAR", "FALTA_ZONA_SUPERIOR", "MOLDE_INCOMPLETO"].includes(status)) {
    await appAlert("El sistema bloquea el avance. No se registrara deslizado desde la vista Operador.", {
      title: "Avance bloqueado",
      type: "danger",
    });
    return;
  }
  await confirmScadaDecision({
    fecha_hora: fechaHora,
    decision_operador: "AVANZAR",
    skip_recent_inspection_check: true,
    avance_cm: recipe.avance_objetivo_cm,
    intervalo_minutos: recipe.intervalo_objetivo_min,
    origen: "manual",
    step_minutes: recipe.intervalo_objetivo_min,
    registrar_avance: true,
    checklist: modal.checklist,
    observacion: observation,
  });
}

async function registerQuickEvent(result) {
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  const decision = result === "correcto" ? "DESLIZAR" : "DETENER";
  const payload = {
    colado_id: state.activeColadoId,
    fecha_hora: state.evaluationTime || formatDatetimeLocal(new Date()),
    minuto_transcurrido: autoMinute(state.evaluationTime || formatDatetimeLocal(new Date())) || "",
    velocidad_deslizamiento_cm_h: state.moldState?.velocidad_real_cm_h || "",
    decision_tomada: decision,
    resultado_fisico: result,
    checklist_no_desmorona: result !== "desmorona",
    checklist_no_se_pega: result !== "se_pega",
    checklist_acabado_aceptable: !["desmorona", "fisura"].includes(result),
    checklist_sin_arrastre: result !== "arrastra",
    observacion: `Preset rapido: ${result}`,
    supervisor: "",
  };
  try {
    await api("/api/eventos", { method: "POST", body: JSON.stringify(payload) });
    await refreshPrediction();
    await refreshMoldState();
    await refreshOperationalData();
  } catch (error) {
    alert("No se pudo registrar evento rapido: " + error.message);
  }
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function registerAdvance(data) {
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  if (isColadoClosed()) return alert("El colado esta finalizado. Reabre el colado antes de registrar avances.");
  if (
    !latestInspectionOk() &&
    !(await appConfirm("No hay una inspeccion OK reciente. Registrar avance manual de todos modos?", {
      title: "Avance sin inspeccion reciente",
      type: "warning",
      confirmText: "Registrar avance",
    }))
  ) return;
  const payload = {
    colado_id: state.activeColadoId,
    avance_cm: data.avance_cm || DEFAULT_ADVANCE_CM,
    fecha_hora: data.fecha_hora || state.evaluationTime || formatDatetimeLocal(new Date()),
    intervalo_minutos: data.intervalo_minutos || "",
    velocidad_real_cm_h: data.velocidad_real_cm_h || "",
    operador: data.operador || "",
    observacion: data.observacion || "",
    origen: data.origen || "manual",
  };
  try {
    const result = await api("/api/avances/registrar-5min", { method: "POST", body: JSON.stringify(payload) });
    if (result.zonas_creadas?.length) {
      const labels = result.zonas_creadas
        .map((zone) => `Zona ${zone.zona_numero}: ${format(zone.elevacion_inferior_cm, 0)}-${format(zone.elevacion_superior_cm, 0)} cm`)
        .join(", ");
      alert(`Zonas creadas: ${labels}`);
    }
    if (data.step_minutes && state.evaluationTime) {
      addEvaluationMinutes(Number(data.step_minutes));
    }
    await refreshMoldState();
    await refreshScadaState();
    await refreshTrends();
  } catch (error) {
    alert("No se pudo registrar avance: " + error.message);
  }
}

async function confirmInspectionFromChecklist() {
  markChecklistOk();
  const checklist = quickChecklistPayload();
  const fechaHora = state.evaluationTime || formatDatetimeLocal(new Date());
  rememberLocalInspection(fechaHora, checklist);
  updateInspectionSignal();
  renderOperationalGuidance();
  await confirmScadaDecision({
    fecha_hora: fechaHora,
    decision_operador: "INSPECCION_OK",
    registrar_avance: false,
    checklist,
    observacion: "Inspeccion fisica confirmada desde checklist rapido.",
  });
}

async function confirmScadaDecision(data) {
  if (!state.activeColadoId) return alert("Selecciona o crea un colado.");
  if (isColadoClosed()) return alert("El colado esta finalizado. Reabre el colado antes de registrar cambios operativos.");
  const colado = activeColado();
  const status = state.moldState?.estado_operativo || "";
  let supervisor = data.supervisor || "";
  if (data.registrar_avance && !data.skip_recent_inspection_check && !latestInspectionOk()) {
    alert("Primero confirma inspeccion fisica. El avance rapido queda bloqueado hasta registrar Inspeccion OK.");
    return;
  }
  if (data.registrar_avance && status === "MOLDE_INCOMPLETO") {
    alert("No se puede registrar avance: primero completa el molde con 4 ollas/zones reales.");
    return;
  }
  if (data.registrar_avance && ["FALTA_ZONA_SUPERIOR", "SIN_ZONA_A_LIBERAR"].includes(status)) {
    alert("No se puede registrar avance: falta la zona superior del molde.");
    return;
  }
  if (data.registrar_avance && status === "NO_LIBERAR" && !data.autorizar_avance_inmaduro) {
    alert("Para avanzar con madurez insuficiente primero marca la zona lista por inspeccion.");
    return;
  }
  if (data.registrar_avance && status === "CRITICO") {
    supervisor = await appPrompt("Este avance va contra una recomendacion critica. Captura el supervisor responsable.", "", {
      title: "Supervisor requerido",
      type: "danger",
      promptLabel: "Supervisor",
      confirmText: "Confirmar",
    }) || "";
    if (!supervisor) return;
  }
  const payload = {
    colado_id: state.activeColadoId,
    fecha_hora: data.fecha_hora || state.evaluationTime || formatDatetimeLocal(new Date()),
    decision_operador: data.decision_operador,
    avance_cm: data.avance_cm || DEFAULT_ADVANCE_CM,
    intervalo_minutos: data.intervalo_minutos || activeAdvanceRecipe().intervalo_objetivo_min,
    velocidad_real_cm_h: data.velocidad_real_cm_h || "",
    registrar_avance: data.registrar_avance,
    autorizar_avance_inmaduro: Boolean(data.autorizar_avance_inmaduro),
    operador: data.operador || colado?.operador || "",
    supervisor,
    origen: data.origen || "manual",
    checklist: data.checklist || {
      no_desmorona: true,
      no_se_pega: true,
      acabado_aceptable: true,
      sin_arrastre: true,
    },
    observacion: data.observacion || "",
  };
  try {
    const result = await api("/api/scada/confirmar-avance", { method: "POST", body: JSON.stringify(payload) });
    if (result.zonas_creadas?.length) {
      const labels = result.zonas_creadas
        .map((zone) => `Zona ${zone.zona_numero}: ${format(zone.elevacion_inferior_cm, 0)}-${format(zone.elevacion_superior_cm, 0)} cm`)
        .join(", ");
      alert(`Zonas creadas: ${labels}`);
    }
    if (data.step_minutes && state.evaluationTime) addEvaluationMinutes(Number(data.step_minutes));
    await refreshPrediction();
    await refreshMoldState();
    await refreshScadaState();
    await refreshTrends();
  } catch (error) {
    if (error.status) {
      alert("No se pudo registrar la decision SCADA: " + error.message);
    } else {
      queueOffline("/api/scada/confirmar-avance", payload);
      alert("Sin conexion: la decision SCADA quedo pendiente de sincronizar.");
    }
  }
}

async function acknowledgeAlarm(id) {
  if (!id) return;
  const colado = activeColado();
  try {
    await api("/api/scada/alarmas/reconocer", {
      method: "POST",
      body: JSON.stringify({ id, operador_reconoce: colado?.operador || "" }),
    });
    await refreshScadaState();
  } catch (error) {
    alert("No se pudo reconocer la alarma: " + error.message);
  }
}

function autoMinute(fechaHora) {
  const colado = activeColado();
  const base =
    firstZoneReferenceTime() ||
    colado?.fecha_hora_inicio ||
    colado?.hora_colocacion_en_molde ||
    colado?.hora_inicio_descarga;
  if (!base) return null;
  const start = new Date(base);
  const current = new Date(fechaHora);
  const minutes = (current - start) / 60000;
  return Number.isFinite(minutes) ? Math.max(0, minutes).toFixed(1) : null;
}

function firstZoneReferenceTime() {
  const zones = [
    ...(state.moldState?.zonas_liberadas || []),
    ...(state.moldState?.zonas_activas || []),
    state.moldState?.zona_en_liberacion,
  ]
    .filter((zone) => zone && !String(zone.id || "").startsWith("pendiente"))
    .filter((zone) => zone.hora_salida_planta || zone.hora_referencia_madurez || zone.hora_inicio_llenado)
    .sort((a, b) => Number(a.zona_numero || 0) - Number(b.zona_numero || 0));
  const first = zones[0];
  return first?.hora_salida_planta || first?.hora_referencia_madurez || first?.hora_inicio_llenado || "";
}

function formatZoneTime(value) {
  if (!value) return "--";
  const text = String(value);
  if (text.includes("T")) return text.replace("T", " ");
  return text;
}

function slideChecklistOk(payload) {
  return ["checklist_no_desmorona", "checklist_no_se_pega", "checklist_acabado_aceptable", "checklist_sin_arrastre"].every(
    (key) => payload[key] === "on"
  );
}

function rememberLocalReading(payload) {
  const key = String(payload.colado_id);
  state.localReadings[key] = state.localReadings[key] || [];
  state.localReadings[key].push(payload);
  localStorage.setItem("localReadings", JSON.stringify(state.localReadings));
}

function queueOffline(path, payload) {
  state.offlineQueue.push({ path, payload });
  localStorage.setItem("offlineQueue", JSON.stringify(state.offlineQueue));
  setConnection(`Pendientes: ${state.offlineQueue.length}`, false);
  renderDiagnostics();
}

async function syncOffline() {
  const remaining = [];
  for (const item of state.offlineQueue) {
    try {
      await api(item.path, { method: "POST", body: JSON.stringify(item.payload) });
    } catch (error) {
      remaining.push(item);
    }
  }
  state.offlineQueue = remaining;
  localStorage.setItem("offlineQueue", JSON.stringify(state.offlineQueue));
  renderDiagnostics();
  await loadBootstrap();
}

function updateLinks() {
  const exportLink = $("#export-link");
  const eventsLink = $("#events-export-link");
  const zonesLink = $("#zones-export-link");
  const advancesLink = $("#advances-export-link");
  const reportLink = $("#report-link");
  if (exportLink) exportLink.href = state.activeColadoId ? `/api/export/lecturas.csv?colado_id=${state.activeColadoId}` : "#";
  if (eventsLink) eventsLink.href = state.activeColadoId ? `/api/export/eventos.csv?colado_id=${state.activeColadoId}` : "#";
  if (zonesLink) zonesLink.href = state.activeColadoId ? `/api/export/zonas.csv?colado_id=${state.activeColadoId}` : "#";
  if (advancesLink) advancesLink.href = state.activeColadoId ? `/api/export/avances.csv?colado_id=${state.activeColadoId}` : "#";
  if (reportLink) reportLink.href = state.activeColadoId ? `/api/report/colado.html?colado_id=${state.activeColadoId}` : "#";
  const central = $("#central-report-link");
  const centralZip = $("#central-zip-link");
  const bitacora = $("#bitacora-export-link");
  const operatorLog = $("#operator-log-export-link");
  const homeDemoExport = $("#home-demo-export-link");
  if (central) central.href = state.activeColadoId ? `/api/report/control-central.html?colado_id=${state.activeColadoId}` : "#";
  if (centralZip) centralZip.href = state.activeColadoId ? `/api/export/control-central.zip?colado_id=${state.activeColadoId}` : "#";
  if (bitacora) bitacora.href = state.activeColadoId ? `/api/export/bitacora.csv?colado_id=${state.activeColadoId}` : "#";
  if (operatorLog) operatorLog.href = state.activeColadoId ? `/api/export/bitacora.csv?colado_id=${state.activeColadoId}` : "#";
  if (homeDemoExport) {
    const colado = activeColado();
    homeDemoExport.href = state.activeColadoId && Number(colado?.es_demo || 0) ? `/api/export/control-central.zip?colado_id=${state.activeColadoId}` : "#";
    homeDemoExport.classList.toggle("disabled", !(state.activeColadoId && Number(colado?.es_demo || 0)));
  }
  const eventSecondary = $("#events-export-link-secondary");
  const zonesSecondary = $("#zones-export-link-secondary");
  const advancesSecondary = $("#advances-export-link-secondary");
  if (eventSecondary) eventSecondary.href = eventsLink?.href || (state.activeColadoId ? `/api/export/eventos.csv?colado_id=${state.activeColadoId}` : "#");
  if (zonesSecondary) zonesSecondary.href = zonesLink?.href || (state.activeColadoId ? `/api/export/zonas.csv?colado_id=${state.activeColadoId}` : "#");
  if (advancesSecondary) advancesSecondary.href = advancesLink?.href || (state.activeColadoId ? `/api/export/avances.csv?colado_id=${state.activeColadoId}` : "#");
  const demoSummary = $("#demo-mode-summary");
  if (demoSummary) {
    const colado = activeColado();
    demoSummary.textContent = Number(colado?.es_demo || 0)
      ? `Demo activa: Colado #${colado.id}. Puedes exportarla o limpiar solo datos demo.`
      : "La demo completa genera zonas, temperatura simulada y avances para entrenamiento.";
  }
}

function arrhenius(tempC, params) {
  const tempK = tempC + 273.15;
  const refK = params.t_ref_c + 273.15;
  return Math.exp((-params.activation_energy_j_mol / params.gas_constant_j_mol_k) * (1 / tempK - 1 / refK));
}

function stateForAdvance(advance) {
  const p = state.bootstrap.params || defaultParams();
  if (advance < p.prepare_threshold) return "ESPERAR";
  if (advance < p.slide_threshold) return "PREPARARSE";
  if (advance <= p.over_maturity_threshold) return "DESLIZAR";
  if (advance <= p.critical_maturity_threshold) return "RIESGO_AGARROTAMIENTO";
  return "CRITICO";
}

function defaultParams() {
  return {
    t_ref_c: 23,
    activation_energy_j_mol: 40000,
    gas_constant_j_mol_k: 8.314,
    target_maturity_h_eq: 7.976855441542278,
    prepare_threshold: 0.7,
    slide_threshold: 0.9,
    over_maturity_threshold: 1.05,
    critical_maturity_threshold: 1.15,
  };
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

setupTabs();
setupEvaluationTime();
setupFormValidation();
loadBootstrap();
