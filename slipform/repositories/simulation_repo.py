"""Repository helpers for deterministic demo/simulation flows."""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from typing import Any

from slipform.domain.validation import parse_datetime
from slipform.repositories.avances_repo import get_active_advance_recipe, insert_mold_advance
from slipform.repositories.catalog_repo import get_reference_points
from slipform.repositories.lecturas_repo import insert_reading


def simulate_curve_readings(
    conn: sqlite3.Connection,
    colado_id: int,
    curve_id: int,
    interval_minutes: float = 5.0,
    replace_existing: bool = False,
) -> int:
    if replace_existing:
        conn.execute("DELETE FROM lecturas WHERE colado_id = ?", (colado_id,))
    points = get_reference_points(conn, curve_id)
    if not points:
        raise ValueError("Curva de referencia sin puntos.")
    minute_offset = min(float(point["minuto"]) for point in points)
    selected: list[dict[str, Any]] = []
    last_minute: float | None = None
    for point in points:
        minute = float(point["minuto"]) - minute_offset
        if last_minute is None or minute - last_minute >= interval_minutes:
            selected.append({**point, "minuto": minute})
            last_minute = minute
    count = 0
    for point in selected:
        insert_reading(
            conn,
            {
                "colado_id": colado_id,
                "minuto_transcurrido": point["minuto"],
                "temperatura_concreto_c": point["temperatura_concreto_c"],
                "origen": "importacion",
            },
        )
        count += 1
    return count


def simulate_operational_advances(
    conn: sqlite3.Connection,
    colado_id: int,
    start_time: str,
    steps: int = 12,
    replace_existing: bool = False,
    operador: str | None = "Simulador",
) -> int:
    if steps <= 0:
        raise ValueError("La simulacion requiere al menos un avance.")
    if replace_existing:
        conn.execute("DELETE FROM avances_molde WHERE colado_id = ?", (colado_id,))
        conn.execute("UPDATE zonas_colado SET avance_generador_id = NULL WHERE colado_id = ?", (colado_id,))
        conn.commit()
    recipe = get_active_advance_recipe(conn, colado_id)
    start = parse_datetime(start_time)
    interval = float(recipe["intervalo_objetivo_min"])
    advance = float(recipe["avance_objetivo_cm"])
    count = 0
    for index in range(steps):
        dt = start + timedelta(minutes=interval * index)
        insert_mold_advance(
            conn,
            {
                "colado_id": colado_id,
                "fecha_hora": dt.isoformat(timespec="minutes"),
                "avance_cm": advance,
                "intervalo_minutos": interval,
                "origen": "simulacion",
                "operador": operador,
                "observacion": "Avance generado por simulador operativo.",
            },
        )
        count += 1
    return count


__all__ = ["simulate_curve_readings", "simulate_operational_advances"]
