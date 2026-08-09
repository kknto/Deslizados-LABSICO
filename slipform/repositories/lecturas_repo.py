"""Repository functions for concrete and ambient readings."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from slipform.domain.validation import (
    optional_float,
    normalize_datetime,
    parse_datetime,
    validate_measurements,
    validate_origin,
)
from slipform.repositories.colados_repo import get_colado


def insert_reading(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    _validate_reading_payload(conn, payload)
    fecha_hora = normalize_datetime(payload.get("fecha_hora") or datetime.now().isoformat(timespec="seconds"))
    minute = resolve_elapsed_minute(conn, int(payload["colado_id"]), fecha_hora, payload.get("minuto_transcurrido"))
    row = conn.execute(
        """
        INSERT INTO lecturas(
            colado_id, sensor_id, fecha_hora, minuto_transcurrido,
            temperatura_concreto_c, temperatura_ambiente_c, humedad_relativa_pct,
            origen, valido, motivo_invalidez
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(payload["colado_id"]),
            _optional_int(payload.get("sensor_id")),
            fecha_hora,
            minute,
            optional_float(payload.get("temperatura_concreto_c")),
            optional_float(payload.get("temperatura_ambiente_c")),
            optional_float(payload.get("humedad_relativa_pct")),
            payload.get("origen") or "manual",
            int(payload.get("valido", 1)),
            payload.get("motivo_invalidez"),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def list_readings(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    return get_readings(conn, colado_id)


def get_readings(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM lecturas
            WHERE colado_id = ? AND valido = 1
            ORDER BY minuto_transcurrido, id
            """,
            (colado_id,),
        ).fetchall()
    ]


def resolve_elapsed_minute(
    conn: sqlite3.Connection,
    colado_id: int,
    fecha_hora: str,
    explicit_minute: Any,
) -> float:
    if explicit_minute not in (None, ""):
        return float(explicit_minute)
    colado = _ensure_existing_colado(conn, colado_id)
    base = (
        _first_zone_reference_time(conn, colado_id)
        or colado.get("fecha_hora_inicio")
        or colado.get("hora_colocacion_en_molde")
        or colado.get("hora_inicio_descarga")
    )
    if not base:
        raise ValueError("No hay hora base del colado para calcular minuto automatico.")
    start = parse_datetime(str(base))
    current = parse_datetime(str(fecha_hora))
    return round((current - start).total_seconds() / 60.0, 3)


def _first_zone_reference_time(conn: sqlite3.Connection, colado_id: int) -> str | None:
    row = conn.execute(
        """
        SELECT COALESCE(hora_salida_planta, hora_referencia_madurez, hora_inicio_llenado) AS hora_base
        FROM zonas_colado
        WHERE colado_id = ?
          AND COALESCE(hora_salida_planta, hora_referencia_madurez, hora_inicio_llenado) IS NOT NULL
          AND COALESCE(hora_salida_planta, hora_referencia_madurez, hora_inicio_llenado) <> ''
        ORDER BY zona_numero ASC, elevacion_inferior_cm ASC, id ASC
        LIMIT 1
        """,
        (colado_id,),
    ).fetchone()
    if not row:
        return None
    return row["hora_base"]


def _validate_reading_payload(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    _ensure_existing_colado(conn, int(payload["colado_id"]))
    validate_origin(payload.get("origen") or "manual")
    validate_measurements(payload)
    minute = payload.get("minuto_transcurrido")
    if minute not in (None, "") and float(minute) < 0:
        raise ValueError("El minuto transcurrido no puede ser negativo.")


def _ensure_existing_colado(conn: sqlite3.Connection, colado_id: int) -> dict[str, Any]:
    colado = get_colado(conn, colado_id)
    if not colado:
        raise ValueError("Colado no encontrado.")
    if str(colado.get("estado") or "").upper() == "CANCELADO":
        raise ValueError("El colado esta cancelado.")
    return colado


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


__all__ = ["get_readings", "insert_reading", "list_readings", "resolve_elapsed_minute"]
