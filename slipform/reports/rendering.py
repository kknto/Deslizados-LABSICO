"""Small rendering helpers for HTML reports."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any


def escape_html(value: object) -> str:
    return (
        str(value if value is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


MONTH_LABELS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def svg_line_chart(
    points: list[dict[str, Any]],
    x_key: str,
    y_key: str,
    expected_speed: float | None = None,
    *,
    x_label_key: str | None = None,
    x_axis_title: str = "",
    y_axis_title: str = "",
    y_tick_step: float | None = None,
    legend: bool = False,
) -> str:
    width, height = 900, 300
    margin_left, margin_right, margin_top, margin_bottom = 72, 24, 42, 62
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    raw = [
        (float(p.get(x_key) or 0), float(p.get(y_key) or 0), _parse_datetime(p.get(x_label_key)) if x_label_key else None)
        for p in points
        if p.get(x_key) is not None and p.get(y_key) is not None
    ]
    if not raw:
        return "<div class='empty-chart'>Sin datos para graficar.</div>"
    raw.sort(key=lambda item: item[0])
    first_x = raw[0][0]
    clean = [(max(0.0, x - first_x), y, dt) for x, y, dt in raw]
    if not clean:
        return "<div class='empty-chart'>Sin datos para graficar.</div>"
    max_x = max(60.0, *(x for x, _, _ in clean))
    max_y = max(1.0, *(y for _, y, _ in clean))
    if expected_speed:
        max_y = max(max_y, (expected_speed / 60.0) * max_x)
    step = _resolve_y_step(max_y, y_tick_step)
    max_y = max(step, math.ceil(max_y / step) * step)
    y_ticks = [round(value, 3) for value in _inclusive_range(0.0, max_y, step)]
    x_ticks = _build_x_ticks(clean, max_x)

    def xy(x: float, y: float) -> str:
        px = margin_left + (x / max_x) * plot_width
        py = margin_top + plot_height - (y / max_y) * plot_height
        return f"{px:.1f},{py:.1f}"

    real = " ".join(xy(x, y) for x, y, _ in clean)
    expected = ""
    if expected_speed:
        target_y = (expected_speed / 60.0) * max_x
        expected = f"<polyline points='{xy(0, 0)} {xy(max_x, target_y)}' fill='none' stroke='#64748b' stroke-width='2.4' stroke-dasharray='7 7'/>"
    y_grid = "\n".join(_y_tick_markup(tick, xy, margin_left, width - margin_right) for tick in y_ticks)
    x_grid = "\n".join(
        _x_tick_markup(tick["x"], tick["label"], max_x, margin_left, plot_width, margin_top, height - margin_bottom)
        for tick in x_ticks
    )
    real_points = "\n".join(_point_markup(x, y, xy) for x, y, _ in _sample_points(clean))
    legend_markup = ""
    if legend:
        legend_markup = f"""
      <g aria-label='Leyenda'>
        <line x1='{margin_left}' y1='18' x2='{margin_left + 30}' y2='18' stroke='#155e75' stroke-width='3'/>
        <text x='{margin_left + 38}' y='22' font-size='12' fill='#172026'>Avance real</text>
        <line x1='{margin_left + 140}' y1='18' x2='{margin_left + 170}' y2='18' stroke='#64748b' stroke-width='2.4' stroke-dasharray='7 7'/>
        <text x='{margin_left + 178}' y='22' font-size='12' fill='#172026'>Avance esperado</text>
      </g>"""
    x_title = f"<text x='{margin_left + plot_width / 2:.1f}' y='{height - 8}' text-anchor='middle' font-size='12' fill='#172026'>{escape_html(x_axis_title)}</text>" if x_axis_title else ""
    y_title = (
        f"<text x='16' y='{margin_top + plot_height / 2:.1f}' transform='rotate(-90 16 {margin_top + plot_height / 2:.1f})' "
        f"text-anchor='middle' font-size='12' fill='#172026'>{escape_html(y_axis_title)}</text>"
        if y_axis_title
        else ""
    )
    return f"""
    <svg viewBox='0 0 {width} {height}' role='img' aria-label='Grafica de avance real contra avance esperado'>
      <rect x='0' y='0' width='{width}' height='{height}' fill='#fbfcfd'/>
      {legend_markup}
      {y_grid}
      {x_grid}
      <line x1='{margin_left}' y1='{margin_top}' x2='{margin_left}' y2='{height - margin_bottom}' stroke='#94a3b8'/>
      <line x1='{margin_left}' y1='{height - margin_bottom}' x2='{width - margin_right}' y2='{height - margin_bottom}' stroke='#94a3b8'/>
      {expected}
      <polyline points='{real}' fill='none' stroke='#155e75' stroke-width='3'/>
      {real_points}
      <text x='{width - margin_right}' y='24' text-anchor='end' font-size='11' fill='#475569'>Duracion {max_x:.0f} min</text>
      {x_title}
      {y_title}
    </svg>
    """


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _format_datetime_label(value: datetime) -> str:
    month = MONTH_LABELS[value.month - 1]
    return f"{value.day:02d}-{month} {value.hour:02d}:{value.minute:02d}"


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def _resolve_y_step(max_y: float, requested: float | None) -> float:
    if requested and max_y >= requested * 3:
        return float(requested)
    target = max_y / 5.0
    for step in (5, 10, 20, 25, 50, 100):
        if target <= step:
            return float(step)
    return float(math.ceil(target / 100.0) * 100)


def _inclusive_range(start: float, stop: float, step: float) -> list[float]:
    values: list[float] = []
    current = start
    while current <= stop + (step / 10.0):
        values.append(current)
        current += step
    return values


def _build_x_ticks(clean: list[tuple[float, float, datetime | None]], max_x: float) -> list[dict[str, Any]]:
    tick_count = 6 if max_x >= 300 else 5
    positions = [round((max_x / (tick_count - 1)) * index, 3) for index in range(tick_count)]
    datetimes = [(x, dt) for x, _, dt in clean if dt is not None]
    if len(datetimes) >= 2:
        first_dt = datetimes[0][1]
        last_dt = datetimes[-1][1]
        total_seconds = max(1.0, (last_dt - first_dt).total_seconds())
        return [
            {
                "x": x,
                "label": _format_datetime_label(first_dt + timedelta(seconds=total_seconds * (x / max_x))),
            }
            for x in positions
        ]
    return [{"x": x, "label": f"{_format_number(x)} min"} for x in positions]


def _sample_points(clean: list[tuple[float, float, datetime | None]]) -> list[tuple[float, float, datetime | None]]:
    if len(clean) <= 60:
        return clean
    step = math.ceil(len(clean) / 60)
    sampled = clean[::step]
    if sampled[-1] != clean[-1]:
        sampled.append(clean[-1])
    return sampled


def _y_tick_markup(tick: float, xy, x1: float, x2: float) -> str:
    _, y = xy(0, tick).split(",")
    return (
        f"<line x1='{x1}' y1='{y}' x2='{x2}' y2='{y}' stroke='#e2e8f0'/>"
        f"<text x='{x1 - 10}' y='{float(y) + 4:.1f}' text-anchor='end' font-size='11' fill='#334155'>"
        f"{_format_number(tick)} cm</text>"
    )


def _x_tick_markup(x: float, label: str, max_x: float, margin_left: float, plot_width: float, y1: float, y2: float) -> str:
    px = margin_left + (x / max_x) * plot_width
    return (
        f"<line x1='{px:.1f}' y1='{y1}' x2='{px:.1f}' y2='{y2}' stroke='#f1f5f9'/>"
        f"<text x='{px:.1f}' y='{y2 + 18}' text-anchor='middle' font-size='11' fill='#334155'>"
        f"{escape_html(label)}</text>"
    )


def _point_markup(x: float, y: float, xy) -> str:
    px, py = xy(x, y).split(",")
    return f"<circle cx='{px}' cy='{py}' r='2.2' fill='#155e75'/>"


__all__ = ["escape_html", "svg_line_chart"]
