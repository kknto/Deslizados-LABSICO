"""Repository functions for sensor health diagnostics."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from slipform.domain.validation import parse_datetime


def get_sensor_health(conn: sqlite3.Connection, colado_id: int | None = None, now_iso: str | None = None) -> list[dict[str, Any]]:
    now = parse_datetime(now_iso) if now_iso else datetime.now()
    where = ""
    params: tuple[Any, ...] = ()
    if colado_id:
        where = "WHERE latest.colado_id = ?"
        params = (colado_id,)
    rows = [
        dict(row)
        for row in conn.execute(
            f"""
            WITH latest AS (
                SELECT l.*
                FROM lecturas l
                JOIN (
                    SELECT COALESCE(sensor_id, 0) AS sid, MAX(fecha_hora) AS fecha_hora
                    FROM lecturas
                    WHERE origen = 'sensor'
                    GROUP BY COALESCE(sensor_id, 0)
                ) x ON COALESCE(l.sensor_id, 0) = x.sid AND l.fecha_hora = x.fecha_hora
                WHERE l.origen = 'sensor'
            )
            SELECT
                COALESCE(s.id, latest.sensor_id, 0) AS sensor_id,
                COALESCE(s.tipo, 'sensor') AS tipo,
                COALESCE(s.variable, 'temperatura') AS variable,
                s.ubicacion,
                s.silo_id,
                s.activo,
                s.fecha_calibracion,
                latest.colado_id,
                latest.fecha_hora AS ultima_fecha_hora,
                latest.temperatura_concreto_c,
                latest.temperatura_ambiente_c,
                latest.humedad_relativa_pct,
                latest.origen
            FROM latest
            LEFT JOIN sensores s ON s.id = latest.sensor_id
            {where}
            ORDER BY sensor_id
            """,
            params,
        ).fetchall()
    ]
    for row in rows:
        last = row.get("ultima_fecha_hora")
        age = (now - parse_datetime(str(last))).total_seconds() / 60.0 if last else None
        row["minutos_sin_senal"] = round(age, 1) if age is not None else None
        row["estado_salud"] = "VENCIDO" if age is not None and age > 10 else "OK"
    return rows


__all__ = ["get_sensor_health"]
