window.SlipformECharts = (() => {
  const { $ } = window.SlipformApp;
  const { format } = window.SlipformUtils;
  const instances = new Map();
  const observed = new WeakSet();

  function available() {
    return Boolean(window.echarts);
  }

  function chart(selector) {
    const el = $(selector);
    if (!el || !available()) return null;
    if (!el.closest(".scada-detail")) {
      el.style.width = "100%";
      el.style.maxWidth = "100%";
    }
    if (!el.style.height) el.style.height = el.getAttribute("data-chart-height") || "320px";
    let instance = instances.get(selector);
    if (!instance || instance.isDisposed?.()) {
      instance = window.echarts.init(el, null, { renderer: "canvas" });
      instances.set(selector, instance);
      observeChart(el, instance);
    }
    return instance;
  }

  function observeChart(el, instance) {
    if (observed.has(el)) return;
    observed.add(el);
    if ("ResizeObserver" in window) {
      const observer = new ResizeObserver(() => {
        window.requestAnimationFrame(() => instance.resize());
      });
      observer.observe(el);
    }
  }

  function pointData(points, yKey) {
    return (points || [])
      .map((point) => [Number(point.minuto ?? point.minuto_transcurrido), Number(point[yKey])])
      .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
  }

  function normalizeExpectedPoints(points, result = null) {
    const sorted = [...(points || [])]
      .map((point) => ({ ...point, minuto: Number(point.minuto ?? point.minuto_transcurrido) }))
      .filter((point) => Number.isFinite(point.minuto))
      .sort((a, b) => a.minuto - b.minuto);
    if (!sorted.length) return [];
    const firstMinute = sorted[0].minuto;
    const thresholdMinute = Number(result?.zona_prediccion?.minuto_umbral_deslizar);
    const looksShiftedFromReference =
      firstMinute > 240 || (Number.isFinite(thresholdMinute) && thresholdMinute >= 0 && thresholdMinute < firstMinute);
    if (!looksShiftedFromReference) return sorted;
    return sorted.map((point) => ({ ...point, minuto: Math.max(0, point.minuto - firstMinute) }));
  }

  function seriesXBounds(seriesGroups, markers = []) {
    const values = [];
    for (const group of seriesGroups || []) {
      for (const point of group || []) {
        const value = Array.isArray(point) ? Number(point[0]) : Number(point?.minuto ?? point?.minuto_transcurrido);
        if (Number.isFinite(value)) values.push(value);
      }
    }
    for (const marker of markers || []) {
      const value = Number(marker.value ?? marker.xAxis);
      if (Number.isFinite(value)) values.push(value);
    }
    if (!values.length) return null;
    const max = Math.max(...values, 60);
    return { min: 0, max: Math.ceil(max / 30) * 30 };
  }

  function statusBackground() {
    const status = window.SlipformApp.state.moldState?.estado_operativo || "";
    if (status === "NO_LIBERAR") return "#fff1f2";
    if (status === "RIESGO_AGARROTAMIENTO") return "#fff7ed";
    if (status === "CONTINUAR") return "#f0fdf4";
    if (status === "PREPARARSE") return "#fffbeb";
    return "#fbfcfd";
  }

  function commonOption(title, suffix = "", compact = false, result = null) {
    const zoneStart = zoneStartTime(result);
    return {
      backgroundColor: statusBackground(),
      title: { text: title, left: 12, top: 8, textStyle: { fontSize: compact ? 13 : 15, color: "#172026" } },
      tooltip: {
        trigger: "axis",
        valueFormatter: (value) => `${format(value, 1)}${suffix}`,
        formatter: zoneStart
          ? (params) => {
              const rows = Array.isArray(params) ? params : [params];
              const minute = Number(rows[0]?.axisValue ?? rows[0]?.value?.[0] ?? 0);
              return [
                `<b>${minuteToClock(zoneStart, minute)}</b>`,
                `<span>min ${format(minute, 1)}</span>`,
                ...rows.map((item) => `${item.marker || ""}${item.seriesName}: ${format(item.value?.[1], 1)}${suffix}`),
              ].join("<br/>");
            }
          : undefined,
      },
      legend: compact ? { show: false } : { top: 10, right: 12 },
      grid: compact
        ? { left: 42, right: 16, top: 44, bottom: 28, containLabel: true }
        : { left: 58, right: 28, top: 58, bottom: 54, containLabel: true },
      dataZoom: compact
        ? [{ type: "inside", filterMode: "none" }]
        : [
            { type: "inside", filterMode: "none" },
            { type: "slider", height: 18, bottom: 18, filterMode: "none" },
          ],
      xAxis: {
        type: "value",
        name: zoneStart ? "hora" : "min",
        nameLocation: "end",
        minInterval: 30,
        axisLabel: {
          formatter: (value) => zoneStart ? minuteToClock(zoneStart, value) : `${format(value, 0)} min`,
        },
        splitLine: { lineStyle: { color: "#e2e8f0" } },
      },
      yAxis: { type: "value", axisLabel: { formatter: `{value}${suffix}` }, splitLine: { lineStyle: { color: "#e2e8f0" } } },
    };
  }

  function zoneStartTime(result) {
    const value =
      result?.zona?.hora_salida_planta ||
      result?.zona?.hora_referencia_madurez ||
      result?.zona_prediccion?.hora_salida_planta;
    if (!value) return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function minuteToClock(start, minute) {
    const date = new Date(start.getTime() + Number(minute || 0) * 60000);
    return date.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
  }

  function emptyGraphic(hasData) {
    return hasData
      ? undefined
      : {
          type: "text",
          left: "center",
          top: "middle",
          style: { text: "Sin datos para graficar", fill: "#5c6b73", fontSize: 16, fontWeight: 700 },
        };
  }

  function markerSeries(markers, yValue, name = "Eventos", color = "#147a4d") {
    const data = (markers || [])
      .map((marker) => [Number(marker.minuto_transcurrido), yValue, marker.resultado_fisico || marker.tipo || name])
      .filter(([x]) => Number.isFinite(x));
    return {
      name,
      type: "scatter",
      data,
      symbolSize: 9,
      itemStyle: { color },
      tooltip: {
        formatter: (params) => `${params.seriesName}<br/>min ${format(params.value[0], 1)}<br/>${params.value[2] || ""}`,
      },
    };
  }

  function renderLineComparison(selector, cfg) {
    const instance = chart(selector);
    if (!instance) return false;
    const option = commonOption(cfg.title, cfg.suffix || "", Boolean(cfg.compact), cfg.result || null);
    const hasData = Boolean((cfg.real || []).length || (cfg.expected || []).length);
    option.yAxis.min = cfg.min ?? null;
    option.yAxis.max = cfg.max ?? null;
    const xBounds = seriesXBounds([cfg.real, cfg.expected, cfg.current ? [cfg.current] : []], cfg.verticalMarkers);
    if (xBounds) {
      option.xAxis.min = xBounds.min;
      option.xAxis.max = xBounds.max;
    }
    option.graphic = emptyGraphic(hasData);
    const markLines = [
      ...(cfg.thresholds || []).map((item) => ({
        name: item.label,
        yAxis: item.value,
        lineStyle: { color: item.color, type: "dashed", width: 2 },
      })),
      ...(cfg.verticalMarkers || []).map((item) => ({
        name: item.label || "Avance",
        xAxis: item.value,
        label: { formatter: item.label || "Avance", color: item.color || "#155e75" },
        lineStyle: { color: item.color || "#155e75", type: item.type || "dotted", width: item.width || 2 },
      })),
    ];
    option.series = [
      {
        name: "Esperada",
        type: "line",
        data: cfg.expected || [],
        smooth: true,
        symbol: "none",
        lineStyle: { width: 2, color: "#64748b", type: "dashed" },
        itemStyle: { color: "#64748b" },
      },
      {
        name: "Real",
        type: "line",
        data: cfg.real || [],
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 3, color: cfg.realColor || "#b42318" },
        itemStyle: { color: cfg.realColor || "#b42318" },
        areaStyle: cfg.area ? { color: "rgba(180,35,24,0.08)" } : undefined,
        markLine: markLines.length ? { symbol: "none", label: { formatter: "{b}" }, data: markLines } : undefined,
      },
      ...(cfg.current
        ? [
            {
              name: "Ahora",
              type: "scatter",
              data: [cfg.current],
              symbolSize: cfg.compact ? 10 : 13,
              itemStyle: { color: "#2563eb", borderColor: "#fff", borderWidth: 2 },
              tooltip: {
                formatter: (params) =>
                  `Ahora<br/>min ${format(params.value[0], 1)}<br/>${format(params.value[1], 1)}${cfg.suffix || ""}<br/>${params.value[2] || ""}`,
              },
            },
          ]
        : []),
      ...(cfg.markers ? [markerSeries(cfg.markers, cfg.markerY ?? 0, "Eventos", "#147a4d")] : []),
      ...(cfg.alarms ? [markerSeries(cfg.alarms, cfg.markerY ?? 0, "Alarmas", "#b42318")] : []),
    ];
    instance.setOption(option, true);
    return true;
  }

  function renderTemperature(selector, result, compact = false) {
    const realSource = result?.temperatura?.real_extendida || result?.temperatura?.real || [];
    const real = realSource;
    const expected = normalizeExpectedPoints(result?.temperatura?.esperada || [], result);
    const current = result?.temperatura?.actual;
    const currentData =
      current && current.temperatura_concreto_c != null
        ? [Number(current.minuto), Number(current.temperatura_concreto_c), current.origen || "actual"]
        : null;
    const advances = compact ? [] : (result?.marcadores?.avances_zona || result?.marcadores?.avances || [])
      .map((advance) => ({
        value: Number(advance.minuto_desde_zona ?? advance.minuto_transcurrido),
        label: `Avance ${format(advance.avance_cm, 1)} cm`,
        color: "#155e75",
      }))
      .filter((item) => Number.isFinite(item.value));
    const thresholdMinute = Number(result?.zona_prediccion?.minuto_umbral_deslizar);
    const thresholdMarker = Number.isFinite(thresholdMinute)
      ? [{ value: thresholdMinute, label: "90% / Deslizar", color: "#147a4d", type: "dashed", width: 3 }]
      : [];
    return renderLineComparison(selector, {
      title: compact ? "Tendencia temperatura" : "Temperatura del concreto: real vs esperada",
      result,
      suffix: " C",
      real: pointData(real, "temperatura_concreto_c"),
      expected: pointData(expected, "temperatura_concreto_c"),
      current: currentData,
      verticalMarkers: [...thresholdMarker, ...advances],
      area: true,
      compact,
      realColor: "#b42318",
    });
  }

  function renderMaturity(selector, result) {
    const thresholdMinute = Number(result?.zona_prediccion?.minuto_umbral_deslizar);
    const expected = normalizeExpectedPoints(result?.madurez?.esperada || [], result);
    return renderLineComparison(selector, {
      title: "Madurez De La Zona",
      result,
      suffix: "%",
      min: 0,
      max: 130,
      real: pointData(result?.madurez?.real || [], "avance_madurez").map(([x, y]) => [x, y * 100]),
      expected: pointData(expected, "avance_madurez").map(([x, y]) => [x, y * 100]),
      realColor: "#155e75",
      markerY: 118,
      markers: result?.marcadores?.eventos || [],
      alarms: result?.marcadores?.alarmas || [],
      verticalMarkers: Number.isFinite(thresholdMinute)
        ? [{ value: thresholdMinute, label: "90% / Deslizar", color: "#147a4d", type: "dashed", width: 3 }]
        : [],
      thresholds: [
        { value: 70, color: "#986f08", label: "70%" },
        { value: 90, color: "#147a4d", label: "90%" },
        { value: 105, color: "#b45309", label: "105%" },
        { value: 115, color: "#b42318", label: "115%" },
      ],
    });
  }

  function renderAdvance(selector, result) {
    return renderLineComparison(selector, {
      title: "Avance Del Molde",
      result,
      suffix: " cm",
      real: pointData(result?.avance?.real || [], "avance_acumulado_cm"),
      expected: pointData(result?.avance?.objetivo || [], "avance_acumulado_cm"),
      realColor: "#155e75",
      markerY: Math.max(30, ...(result?.avance?.real || []).map((p) => Number(p.avance_acumulado_cm) || 0)),
      markers: result?.marcadores?.avances || [],
      alarms: result?.marcadores?.alarmas || [],
    });
  }

  function renderZoneMaturity(selector, zones) {
    const instance = chart(selector);
    if (!instance) return false;
    const data = (zones || []).map((zone) => ({
      name: `Z${zone.zona_numero}`,
      value: Number(zone.avance_madurez || 0) * 100,
      itemStyle: { color: zoneColor(Number(zone.avance_madurez || 0) * 100) },
    }));
    instance.setOption(
      {
        backgroundColor: statusBackground(),
        title: { text: "Madurez Por Zona", left: 12, top: 8, textStyle: { fontSize: 15, color: "#172026" } },
        tooltip: { trigger: "axis", valueFormatter: (value) => `${format(value, 1)}%` },
        graphic: emptyGraphic(data.length > 0),
        grid: { left: 54, right: 24, top: 58, bottom: 42, containLabel: true },
        xAxis: { type: "category", data: data.map((item) => item.name) },
        yAxis: { type: "value", min: 0, max: 130, axisLabel: { formatter: "{value}%" } },
        series: [
          {
            name: "Madurez",
            type: "bar",
            data,
            barMaxWidth: 42,
            markLine: {
              symbol: "none",
              data: [
                { name: "90%", yAxis: 90, lineStyle: { color: "#147a4d", type: "dashed" } },
                { name: "105%", yAxis: 105, lineStyle: { color: "#b45309", type: "dashed" } },
                { name: "115%", yAxis: 115, lineStyle: { color: "#b42318", type: "dashed" } },
              ],
            },
          },
        ],
      },
      true
    );
    return true;
  }

  function zoneColor(value) {
    if (value < 70) return "#b42318";
    if (value < 90) return "#d97706";
    if (value <= 105) return "#147a4d";
    return "#b45309";
  }

  function resizeAll() {
    window.requestAnimationFrame(() => {
      for (const instance of instances.values()) instance.resize();
    });
  }

  window.addEventListener("resize", resizeAll);

  return {
    available,
    renderAdvance,
    renderMaturity,
    renderTemperature,
    renderZoneMaturity,
    resizeAll,
  };
})();
