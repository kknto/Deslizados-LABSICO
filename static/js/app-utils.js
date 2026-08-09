window.SlipformUtils = (() => {
  function toDatetimeLocalValue(value) {
    if (!value) return "";
    return String(value).slice(0, 16);
  }

  function formatDatetimeLocal(date) {
    const pad = (value) => String(value).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(
      date.getMinutes()
    )}`;
  }

  function stateClass(value) {
    if (value === "ESPERAR") return "state-esperar";
    if (value === "PREPARARSE") return "state-prepararse";
    if (value === "DESLIZAR") return "state-deslizar";
    if (value === "RIESGO_AGARROTAMIENTO" || value === "RIESGO_RETARDO") return "state-risk";
    if (value === "CRITICO" || value === "SENSOR_INVALIDO") return "state-critical";
    return "state-empty";
  }

  function moldStateClass(value) {
    if (value === "CERRADO") return "state-closed";
    if (value === "CONTINUAR") return "state-deslizar";
    if (value === "PREPARARSE" || value === "SIN_ZONA_A_LIBERAR" || value === "MOLDE_INCOMPLETO") return "state-prepararse";
    if (value === "RIESGO_AGARROTAMIENTO") return "state-risk";
    if (value === "NO_LIBERAR") return "state-critical";
    return "state-empty";
  }

  function format(value, digits) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(digits) : "--";
  }

  function formatBytes(value) {
    const bytes = Number(value);
    if (!Number.isFinite(bytes)) return "--";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  return {
    escapeHtml,
    format,
    formatBytes,
    formatDatetimeLocal,
    moldStateClass,
    stateClass,
    toDatetimeLocalValue,
  };
})();
