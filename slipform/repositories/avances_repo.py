"""Repository functions for mold advances and advance recipes."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from slipform.config import (
    DEFAULT_ADVANCE_CM,
    DEFAULT_ADVANCE_INTERVAL_MIN,
    DEFAULT_ADVANCE_SPEED_CM_H,
    DEFAULT_ADVANCE_TOLERANCE_CM_H,
)
from slipform.domain.validation import normalize_datetime, optional_float, parse_datetime, validate_advance_values
from slipform.repositories.colados_repo import get_colado
from slipform.repositories.mold_config_repo import default_advance_recipe, get_mold_config
from slipform.repositories.zonas_repo import ensure_continuous_zones


def insert_mold_advance(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    _validate_advance_payload(conn, payload)
    colado_id = int(payload["colado_id"])
    cfg = get_mold_config(conn)
    recipe = get_active_advance_recipe(conn, colado_id)
    fecha_hora = normalize_datetime(payload.get("fecha_hora") or datetime.now().isoformat(timespec="seconds"))
    colado = _ensure_existing_colado(conn, colado_id)
    base = colado.get("hora_colocacion_en_molde") or colado.get("hora_inicio_descarga") or colado.get("fecha_hora_inicio")
    minute = payload.get("minuto_transcurrido")
    if minute in (None, ""):
        minute = (parse_datetime(fecha_hora) - parse_datetime(str(base))).total_seconds() / 60.0
    previous = conn.execute(
        """
        SELECT id, avance_acumulado_cm, fecha_hora
        FROM avances_molde
        WHERE colado_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (colado_id,),
    ).fetchone()
    advance = float(payload.get("avance_cm") or recipe["avance_objetivo_cm"] or cfg["avance_objetivo_cm_5min"])
    interval_minutes = optional_float(payload.get("intervalo_minutos") or payload.get("intervalo_objetivo_min"))
    if interval_minutes is None:
        interval_minutes = optional_float(recipe.get("intervalo_objetivo_min"))
    accumulated = optional_float(payload.get("avance_acumulado_cm"))
    if accumulated is None:
        accumulated = (float(previous["avance_acumulado_cm"]) if previous else 0.0) + advance
    speed = _resolve_speed(payload, recipe, cfg, previous, fecha_hora, advance, interval_minutes)
    row = conn.execute(
        """
        INSERT INTO avances_molde(
            colado_id, receta_avance_id, fecha_hora, minuto_transcurrido, avance_cm,
            avance_acumulado_cm, velocidad_real_cm_h, intervalo_minutos,
            origen, observacion, operador
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            colado_id,
            _optional_int(recipe.get("id")),
            fecha_hora,
            round(float(minute), 3),
            advance,
            accumulated,
            speed,
            interval_minutes,
            payload.get("origen") or "manual",
            payload.get("observacion"),
            payload.get("operador"),
        ),
    ).fetchone()
    item_id = int(row["id"])
    if payload.get("asegurar_continuidad", True):
        ensure_continuous_zones(
            conn,
            colado_id,
            float(previous["avance_acumulado_cm"]) if previous else 0.0,
            float(accumulated),
            fecha_hora,
            previous_fecha_hora=str(previous["fecha_hora"]) if previous else None,
            advance_id=item_id,
        )
    conn.commit()
    return item_id


def list_mold_advances(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    return get_advances(conn, colado_id)


def get_advances(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM avances_molde
            WHERE colado_id = ?
            ORDER BY fecha_hora, id
            """,
            (colado_id,),
        ).fetchall()
    ]


def latest_advance_cm(conn: sqlite3.Connection, colado_id: int) -> float:
    row = conn.execute(
        """
        SELECT avance_acumulado_cm
        FROM avances_molde
        WHERE colado_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (colado_id,),
    ).fetchone()
    return float(row["avance_acumulado_cm"]) if row else 0.0


def get_active_advance_recipe(conn: sqlite3.Connection, colado_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT *
        FROM recetas_avance_colado
        WHERE colado_id = ? AND activo = 1
        ORDER BY id DESC
        LIMIT 1
        """,
        (colado_id,),
    ).fetchone()
    return dict(row) if row else default_advance_recipe(conn, colado_id)


def upsert_advance_recipe(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    colado_id = int(payload["colado_id"])
    advance = optional_float(payload.get("avance_objetivo_cm"))
    interval = optional_float(payload.get("intervalo_objetivo_min") or payload.get("intervalo_minutos"))
    if advance is None:
        advance = DEFAULT_ADVANCE_CM
    if interval is None:
        interval = DEFAULT_ADVANCE_INTERVAL_MIN
    if advance <= 0 or interval <= 0:
        raise ValueError("La receta requiere avance e intervalo mayores a cero.")
    speed = advance / (interval / 60.0)
    min_speed = optional_float(payload.get("tolerancia_velocidad_min_cm_h"))
    max_speed = optional_float(payload.get("tolerancia_velocidad_max_cm_h"))
    if min_speed is None:
        min_speed = max(0.0, speed - DEFAULT_ADVANCE_TOLERANCE_CM_H)
    if max_speed is None:
        max_speed = speed + DEFAULT_ADVANCE_TOLERANCE_CM_H
    if min_speed < 0 or max_speed <= 0 or min_speed > max_speed:
        raise ValueError("La tolerancia de velocidad no es valida.")
    motivo = str(payload.get("motivo") or "").strip()
    if not motivo:
        motivo = "Ajuste de receta de avance."
    conn.execute("UPDATE recetas_avance_colado SET activo = 0 WHERE colado_id = ?", (colado_id,))
    row = conn.execute(
        """
        INSERT INTO recetas_avance_colado(
            colado_id, fecha_hora, avance_objetivo_cm, intervalo_objetivo_min,
            velocidad_objetivo_cm_h, tolerancia_velocidad_min_cm_h,
            tolerancia_velocidad_max_cm_h, activo, motivo, operador, supervisor
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        RETURNING id
        """,
        (
            colado_id,
            normalize_datetime(payload.get("fecha_hora") or datetime.now().isoformat(timespec="seconds")),
            advance,
            interval,
            speed,
            min_speed,
            max_speed,
            motivo,
            payload.get("operador"),
            payload.get("supervisor"),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def update_advance_recipe(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    return upsert_advance_recipe(conn, payload)


def list_advance_recipes(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM recetas_avance_colado
            WHERE colado_id = ?
            ORDER BY id DESC
            """,
            (colado_id,),
        ).fetchall()
    ]


def _validate_advance_payload(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    _ensure_existing_colado(conn, int(payload["colado_id"]))
    validate_advance_values(payload)


def _ensure_existing_colado(conn: sqlite3.Connection, colado_id: int) -> dict[str, Any]:
    colado = get_colado(conn, colado_id)
    if not colado:
        raise ValueError("Colado no encontrado.")
    if str(colado.get("estado") or "").upper() == "CANCELADO":
        raise ValueError("El colado esta cancelado.")
    return colado


def _resolve_speed(
    payload: dict[str, Any],
    recipe: dict[str, Any],
    cfg: dict[str, Any],
    previous: sqlite3.Row | None,
    fecha_hora: str,
    advance: float,
    interval_minutes: float | None,
) -> float | None:
    speed = optional_float(payload.get("velocidad_real_cm_h"))
    if speed is None and interval_minutes and interval_minutes > 0:
        return advance / (interval_minutes / 60.0)
    if speed is None and previous:
        elapsed_h = (parse_datetime(fecha_hora) - parse_datetime(str(previous["fecha_hora"]))).total_seconds() / 3600.0
        return advance / elapsed_h if elapsed_h > 0 else None
    if speed is None:
        return recipe.get("velocidad_objetivo_cm_h") or cfg.get("velocidad_objetivo_cm_h")
    return speed


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


__all__ = [
    "get_active_advance_recipe",
    "get_advances",
    "insert_mold_advance",
    "latest_advance_cm",
    "list_advance_recipes",
    "list_mold_advances",
    "update_advance_recipe",
    "upsert_advance_recipe",
]
