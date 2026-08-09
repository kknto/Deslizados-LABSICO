window.SlipformCharts = (() => {
  const { $ } = window.SlipformApp;
  const { format } = window.SlipformUtils;

  function drawTrendChart(selector, cfg) {
    const canvas = $(selector);
    if (!canvas) return;
    if (typeof canvas.getContext !== "function") {
      canvas.innerHTML = `<div class="empty-chart">Grafica no disponible.</div>`;
      return;
    }
    const ctx = canvas.getContext("2d");
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = statusBackground();
    ctx.fillRect(0, 0, width, height);
    const real = cfg.real || [];
    const expected = cfg.expected || [];
    if (!real.length && !expected.length) {
      drawEmptyChart(ctx, width, height);
      return;
    }
    const minutes = [...real, ...expected].map((p) => Number(p.minuto)).filter(Number.isFinite);
    const yValues = [
      ...real.map(cfg.realY).filter(Number.isFinite),
      ...expected.map(cfg.expectedY).filter(Number.isFinite),
    ];
    const maxMinute = Math.max(60, ...minutes);
    const minY = Math.min(cfg.minDefault, ...yValues) - (cfg.compact ? 1 : 2);
    const maxY = Math.max(cfg.maxDefault, ...yValues) + (cfg.compact ? 1 : 2);
    const margin = cfg.compact
      ? { left: 46, right: 20, top: 16, bottom: 28 }
      : { left: 58, right: 30, top: 24, bottom: 38 };
    const x = (minute) => margin.left + (Number(minute) / maxMinute) * (width - margin.left - margin.right);
    const y = (value) => height - margin.bottom - ((Number(value) - minY) / (maxY - minY)) * (height - margin.top - margin.bottom);
    drawAxesGeneric(ctx, width, height, margin, minY, maxY, maxMinute, cfg.suffix || "");
    for (const threshold of cfg.thresholds || []) {
      if (threshold.value < minY || threshold.value > maxY) continue;
      ctx.save();
      ctx.strokeStyle = threshold.color;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(x(0), y(threshold.value));
      ctx.lineTo(x(maxMinute), y(threshold.value));
      ctx.stroke();
      ctx.fillStyle = threshold.color;
      ctx.fillText(threshold.label, x(maxMinute) - 34, y(threshold.value) - 4);
      ctx.restore();
    }
    drawLine(ctx, expected, (p) => x(p.minuto), (p) => y(cfg.expectedY(p)), "#64748b", 2, [6, 6]);
    drawLine(ctx, real, (p) => x(p.minuto), (p) => y(cfg.realY(p)), "#b42318", 3);
    for (const marker of cfg.markers || []) {
      const minute = Number(marker.minuto_transcurrido);
      if (!Number.isFinite(minute)) continue;
      ctx.fillStyle = "#147a4d";
      ctx.beginPath();
      ctx.arc(x(minute), y(Math.min(maxY, minY + (maxY - minY) * 0.88)), 5, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function drawAxesGeneric(ctx, width, height, margin, minValue, maxValue, maxMinute, suffix) {
    ctx.strokeStyle = "#cbd5db";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(margin.left, margin.top);
    ctx.lineTo(margin.left, height - margin.bottom);
    ctx.lineTo(width - margin.right, height - margin.bottom);
    ctx.stroke();
    ctx.fillStyle = "#5c6b73";
    ctx.font = "12px Segoe UI, Arial";
    ctx.fillText(`${Math.round(maxValue)}${suffix}`, 10, margin.top + 5);
    ctx.fillText(`${Math.round(minValue)}${suffix}`, 10, height - margin.bottom);
    ctx.fillText("0 min", margin.left, height - 12);
    ctx.fillText(`${Math.round(maxMinute)} min`, width - margin.right - 78, height - 12);
  }

  function statusBackground() {
    const status = window.SlipformApp.state.moldState?.estado_operativo || "";
    if (status === "NO_LIBERAR") return "#fff1f2";
    if (status === "RIESGO_AGARROTAMIENTO") return "#fff7ed";
    if (status === "CONTINUAR") return "#f0fdf4";
    if (status === "PREPARARSE") return "#fffbeb";
    return "#fbfcfd";
  }

  function drawEmptyChart(ctx, width, height) {
    ctx.strokeStyle = "#d6dde1";
    ctx.strokeRect(10, 10, width - 20, height - 20);
    ctx.fillStyle = "#5c6b73";
    ctx.font = "16px Segoe UI, Arial";
    ctx.fillText("Sin lecturas para graficar.", 30, 50);
  }

  function drawAxes(ctx, width, height, margin, minTemp, maxTemp, maxMinute) {
    ctx.strokeStyle = "#cbd5db";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(margin.left, margin.top);
    ctx.lineTo(margin.left, height - margin.bottom);
    ctx.lineTo(width - margin.right, height - margin.bottom);
    ctx.stroke();
    ctx.fillStyle = "#5c6b73";
    ctx.font = "12px Segoe UI, Arial";
    ctx.fillText(`${Math.round(maxTemp)} C`, 10, margin.top + 5);
    ctx.fillText(`${Math.round(minTemp)} C`, 10, height - margin.bottom);
    ctx.fillText("0 min", margin.left, height - 12);
    ctx.fillText(`${Math.round(maxMinute)} min`, width - margin.right - 70, height - 12);
  }

  function drawThreshold(ctx, x, y, maxMinute, value, color, label) {
    ctx.save();
    ctx.strokeStyle = color;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(x(0), y(value));
    ctx.lineTo(x(maxMinute), y(value));
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = color;
    ctx.fillText(label, x(maxMinute) - 32, y(value) - 4);
    ctx.restore();
  }

  function drawLine(ctx, points, getX, getY, color, width = 2, dash = []) {
    const clean = points.filter((p) => Number.isFinite(getX(p)) && Number.isFinite(getY(p)));
    if (clean.length < 2) return;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.setLineDash(dash);
    ctx.beginPath();
    ctx.moveTo(getX(clean[0]), getY(clean[0]));
    for (const point of clean.slice(1)) ctx.lineTo(getX(point), getY(point));
    ctx.stroke();
    ctx.restore();
  }

  return {
    drawAxes,
    drawAxesGeneric,
    drawEmptyChart,
    drawLine,
    drawThreshold,
    drawTrendChart,
  };
})();
