"""Small rendering helpers for HTML reports."""

from __future__ import annotations

from typing import Any


def escape_html(value: object) -> str:
    return (
        str(value if value is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def svg_line_chart(points: list[dict[str, Any]], x_key: str, y_key: str, expected_speed: float | None = None) -> str:
    width, height = 760, 220
    margin = 34
    raw = [
        (float(p.get(x_key) or 0), float(p.get(y_key) or 0))
        for p in points
        if p.get(x_key) is not None and p.get(y_key) is not None
    ]
    if not raw:
        return "<div class='empty-chart'>Sin datos para graficar.</div>"
    raw.sort(key=lambda item: item[0])
    first_x = raw[0][0]
    clean = [(max(0.0, x - first_x), y) for x, y in raw]
    if not clean:
        return "<div class='empty-chart'>Sin datos para graficar.</div>"
    max_x = max(60.0, *(x for x, _ in clean))
    max_y = max(1.0, *(y for _, y in clean))
    if expected_speed:
        max_y = max(max_y, (expected_speed / 60.0) * max_x)

    def xy(x: float, y: float) -> str:
        px = margin + (x / max_x) * (width - margin * 2)
        py = height - margin - (y / max_y) * (height - margin * 2)
        return f"{px:.1f},{py:.1f}"

    real = " ".join(xy(x, y) for x, y in clean)
    expected = ""
    if expected_speed:
        target_y = (expected_speed / 60.0) * max_x
        expected = f"<polyline points='{xy(0, 0)} {xy(max_x, target_y)}' fill='none' stroke='#64748b' stroke-width='2' stroke-dasharray='6 6'/>"
    return f"""
    <svg viewBox='0 0 {width} {height}' role='img' aria-label='Grafica de avance'>
      <rect x='0' y='0' width='{width}' height='{height}' fill='#fbfcfd'/>
      <line x1='{margin}' y1='{margin}' x2='{margin}' y2='{height - margin}' stroke='#cbd5db'/>
      <line x1='{margin}' y1='{height - margin}' x2='{width - margin}' y2='{height - margin}' stroke='#cbd5db'/>
      {expected}
      <polyline points='{real}' fill='none' stroke='#155e75' stroke-width='3'/>
      <text x='{margin}' y='{height - 8}' font-size='12'>0 min</text>
      <text x='{width - 130}' y='{height - 8}' font-size='12'>Duracion {max_x:.0f} min</text>
      <text x='8' y='{margin}' font-size='12'>{max_y:.1f}</text>
    </svg>
    """


__all__ = ["escape_html", "svg_line_chart"]
