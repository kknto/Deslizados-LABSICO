window.SlipformOperationalView = (() => {
  const { $, api, state } = window.SlipformApp;
  const { escapeHtml, format, formatBytes, moldStateClass } = window.SlipformUtils;

  function renderSensors() {
    const sensors = state.bootstrap.sensores || [];
    $("#sensors-table").innerHTML =
      sensors.length === 0
        ? `<tr><td colspan="6">Sin lecturas automaticas recibidas.</td></tr>`
        : sensors
            .map(
              (s) => `<tr>
                <td>${escapeHtml(s.sensor)}</td>
                <td>${escapeHtml(s.ultima_fecha_hora)}</td>
                <td>${escapeHtml(s.colado_id)}</td>
                <td>${format(s.temperatura_concreto_c, 1)} C</td>
                <td>${format(s.temperatura_ambiente_c, 1)} C</td>
                <td>${format(s.humedad_relativa_pct, 1)}%</td>
              </tr>`
            )
            .join("");
  }

  function renderProjectForm() {
    const form = $("#project-form");
    const project = state.bootstrap.proyecto || {};
    if (!form) return;
    for (const [key, value] of Object.entries(project)) {
      if (form.elements[key]) form.elements[key].value = value ?? "";
    }
  }

  function renderOperationalData(activeColado) {
    renderHomeSummary(activeColado);
    renderTurnos();
    renderPhotos();
    renderDesplomes();
    renderSensorHealth();
    renderAdjustments();
    renderLearningMatrix();
  }

  async function refreshDiagnostics() {
    try {
      state.diagnostics = await api("/api/health");
      renderDiagnostics();
    } catch (error) {
      state.diagnostics = null;
      renderDiagnostics();
    }
  }

  function renderDiagnostics() {
    const summary = $("#diagnostics-summary");
    const backupsTable = $("#backups-table");
    const auditTable = $("#audit-table");
    const counts = $("#database-counts");
    const queue = $("#offline-queue-summary");
    if (queue) {
      queue.textContent = state.offlineQueue.length
        ? `${state.offlineQueue.length} captura(s) pendientes de sincronizar.`
        : "Sin pendientes.";
    }
    if (!summary || !backupsTable || !counts) return;
    const health = state.diagnostics;
    if (!health) {
      summary.innerHTML = `
        <div><span>Servidor</span><strong>Sin conexion</strong></div>
        <div><span>Base de datos</span><strong>--</strong></div>
        <div><span>Schema</span><strong>--</strong></div>
        <div><span>Cache</span><strong>--</strong></div>
      `;
      backupsTable.innerHTML = `<tr><td colspan="4">No se pudo leer diagnostico.</td></tr>`;
      if (auditTable) auditTable.innerHTML = `<tr><td colspan="6">No se pudo leer auditoria.</td></tr>`;
      counts.innerHTML = "";
      return;
    }
    const sqlite = health.sqlite || {};
    const database = health.database || {};
    const engine = database.engine || sqlite.engine || "sqlite";
    const schema = sqlite.schema || {};
    const frontend = health.frontend || {};
    summary.innerHTML = `
      <div><span>Servidor</span><strong>${health.ok ? "OK" : "ERROR"}</strong></div>
      <div><span>Base de datos</span><strong>${escapeHtml(engine === "postgres" ? "PostgreSQL" : formatBytes(sqlite.bytes || 0))}</strong></div>
      <div><span>Schema</span><strong>v${escapeHtml(schema.version || 0)}</strong></div>
      <div><span>Cache</span><strong>${escapeHtml(frontend.service_worker || "--")}</strong></div>
    `;
    api("/api/backups")
      .then((result) => renderBackups(result.backups || []))
      .catch(() => {
        backupsTable.innerHTML = `<tr><td colspan="4">Sin informacion de backups.</td></tr>`;
      });
    api("/api/auditoria?limit=25")
      .then((result) => renderAudit(result.auditoria || []))
      .catch(() => {
        if (auditTable) auditTable.innerHTML = `<tr><td colspan="6">Sin informacion de auditoria.</td></tr>`;
      });
    counts.innerHTML = Object.entries((database.counts || sqlite.counts) || {})
      .map(([key, value]) => `<div><span>${escapeHtml(key)}</span><strong>${escapeHtml(value)}</strong></div>`)
      .join("");
  }

  function renderAudit(rows) {
    const table = $("#audit-table");
    if (!table) return;
    table.innerHTML =
      rows.length === 0
        ? `<tr><td colspan="6">Sin auditoria registrada.</td></tr>`
        : rows
            .map(
              (row) => `<tr>
                <td>${escapeHtml(row.fecha_hora)}</td>
                <td>${escapeHtml(row.accion)}</td>
                <td>${escapeHtml(row.entidad)} #${escapeHtml(row.entidad_id || "")}</td>
                <td>${escapeHtml(row.colado_id || "")}</td>
                <td>${escapeHtml(row.operador || "")}</td>
                <td>${escapeHtml(row.motivo || "")}</td>
              </tr>`
            )
            .join("");
  }

  function renderBackups(backups) {
    const table = $("#backups-table");
    if (!table) return;
    table.innerHTML =
      backups.length === 0
        ? `<tr><td colspan="4">Sin backups registrados.</td></tr>`
        : backups
            .map(
              (backup) => `<tr>
                <td>${escapeHtml(backup.fecha_hora)}</td>
                <td>${escapeHtml(backup.nombre)}</td>
                <td>${formatBytes(backup.bytes)}</td>
                <td>${escapeHtml(backup.ruta)}</td>
              </tr>`
            )
            .join("");
  }

  function renderHomeSummary(activeColado) {
    const badge = $("#home-state-badge");
    const summary = $("#home-summary");
    if (!badge || !summary) return;
    const status = state.moldState?.estado_operativo || state.latestPrediction?.estado || "SIN_DATOS";
    badge.textContent = status.replaceAll("_", " ");
    badge.className = `state ${moldStateClass(status)}`;
    const colado = activeColado();
    if (!colado) {
      summary.textContent = "Selecciona un colado para iniciar.";
      return;
    }
    const zone = state.moldState?.zona_en_liberacion;
    summary.textContent = `${colado.es_demo ? "DEMO - " : ""}Colado #${colado.id}. ${
      zone ? `Zona proxima ${zone.zona_numero}, madurez ${format(zone.avance_madurez * 100, 1)}%.` : "Genera zonas para evaluar."
    }`;
  }

  function renderTurnos() {
    const table = $("#turnos-table");
    if (!table) return;
    const rows = state.operationalData.turnos || [];
    table.innerHTML =
      rows.length === 0
        ? `<tr><td colspan="8">Sin turnos registrados.</td></tr>`
        : rows
            .map(
              (t) => `<tr>
                <td>${escapeHtml(t.turno)}</td>
                <td>${escapeHtml(t.inicio_turno)}</td>
                <td>${escapeHtml(t.fin_turno)}</td>
                <td>${escapeHtml(t.operador)}</td>
                <td>${format(t.avance_parcial_m, 3)} m</td>
                <td>${format(t.avance_acumulado_m, 3)} m</td>
                <td>${format(t.ritmo_cm_h, 1)} cm/h</td>
                <td>${escapeHtml(t.observaciones)}</td>
              </tr>`
            )
            .join("");
  }

  function renderPhotos() {
    const list = $("#photos-list");
    if (!list) return;
    const rows = state.operationalData.fotografias || [];
    list.innerHTML =
      rows.length === 0
        ? `<div class="photo-empty">Sin fotografias registradas.</div>`
        : rows
            .map(
              (f) => `<figure class="photo-card">
                ${
                  f.imagen_data_url
                    ? `<img src="${escapeHtml(f.imagen_data_url)}" alt="${escapeHtml(f.descripcion || "Fotografia")}" />`
                    : `<div class="photo-empty">Sin imagen</div>`
                }
                <figcaption>
                  <strong>${escapeHtml(f.fecha_hora)}</strong>
                  <span>${escapeHtml(f.zona_numero ? "Zona " + f.zona_numero : "")} ${format(f.elevacion_cm, 1)} cm</span>
                  <span>${escapeHtml(f.descripcion || "")}</span>
                </figcaption>
              </figure>`
            )
            .join("");
  }

  function renderDesplomes() {
    const table = $("#desplomes-table");
    if (!table) return;
    const rows = state.operationalData.desplomes || [];
    table.innerHTML =
      rows.length === 0
        ? `<tr><td colspan="7">Sin lecturas de desplome.</td></tr>`
        : rows
            .map(
              (d) => `<tr>
                <td>${escapeHtml(d.fecha_hora)}</td>
                <td>${escapeHtml(d.punto)}</td>
                <td>${escapeHtml(d.direccion)}</td>
                <td>${format(d.lectura_mm, 1)} mm</td>
                <td>${format(d.tolerancia_mm, 1)} mm</td>
                <td><span class="status-pill ${d.estado === "OK" ? "ok" : "bad"}">${escapeHtml(d.estado)}</span></td>
                <td>${escapeHtml(d.operador)}</td>
              </tr>`
            )
            .join("");
  }

  function renderSensorHealth() {
    const table = $("#sensor-health-table");
    if (!table) return;
    const rows = state.operationalData.sensores || [];
    table.innerHTML =
      rows.length === 0
        ? `<tr><td colspan="9">Sin sensores automaticos recibidos para este colado.</td></tr>`
        : rows
            .map(
              (s) => `<tr>
                <td>${escapeHtml(s.sensor_id)}</td>
                <td>${escapeHtml(s.variable)}</td>
                <td>${escapeHtml(s.ubicacion || s.silo_id || "")}</td>
                <td>${escapeHtml(s.ultima_fecha_hora)}</td>
                <td>${format(s.minutos_sin_senal, 1)}</td>
                <td><span class="status-pill ${s.estado_salud === "OK" ? "ok" : "bad"}">${escapeHtml(s.estado_salud)}</span></td>
                <td>${format(s.temperatura_concreto_c, 1)} C</td>
                <td>${format(s.temperatura_ambiente_c, 1)} C</td>
                <td>${format(s.humedad_relativa_pct, 1)}%</td>
              </tr>`
            )
            .join("");
  }

  function renderAdjustments() {
    const table = $("#adjustments-table");
    const select = $("#adjustment-mezcla-select");
    if (select) {
      select.innerHTML = (state.bootstrap.mezclas || [])
        .map((m) => `<option value="${m.id}">${escapeHtml(m.nombre)}</option>`)
        .join("");
    }
    if (!table) return;
    const rows = state.operationalData.ajustes || [];
    table.innerHTML =
      rows.length === 0
        ? `<tr><td colspan="7">Sin ajustes registrados.</td></tr>`
        : rows
            .map(
              (a) => `<tr>
                <td>${escapeHtml(a.fecha_hora)}</td>
                <td>${escapeHtml(a.mezcla_nombre)}</td>
                <td>${format(a.madurez_objetivo_h_eq, 4)}</td>
                <td>${format(a.umbral_deslizar, 2)}</td>
                <td>${escapeHtml(a.operador)}</td>
                <td>${escapeHtml(a.supervisor)}</td>
                <td>${escapeHtml(a.justificacion)}</td>
              </tr>`
            )
            .join("");
  }

  function renderLearningMatrix() {
    const el = $("#learning-matrix");
    if (!el) return;
    const events = state.latestPrediction?.eventos || [];
    const counts = {
      correcto: events.filter((e) => e.resultado_fisico === "correcto").length,
      temprano: events.filter((e) => ["desmorona", "arrastra", "fisura"].includes(e.resultado_fisico)).length,
      tardio: events.filter((e) => e.resultado_fisico === "se_pega").length,
      alarmas: state.operationalData.ajustes?.length || 0,
    };
    el.innerHTML = `
      <div><span>Avance correcto</span><strong>${counts.correcto}</strong></div>
      <div><span>Posible temprano</span><strong>${counts.temprano}</strong></div>
      <div><span>Posible tardio</span><strong>${counts.tardio}</strong></div>
      <div><span>Ajustes modelo</span><strong>${counts.alarmas}</strong></div>
    `;
  }

  return {
    refreshDiagnostics,
    renderAdjustments,
    renderDesplomes,
    renderDiagnostics,
    renderHomeSummary,
    renderLearningMatrix,
    renderOperationalData,
    renderPhotos,
    renderProjectForm,
    renderSensorHealth,
    renderSensors,
    renderTurnos,
  };
})();
