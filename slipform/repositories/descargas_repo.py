"""Repository functions for concrete truck/load records."""

from __future__ import annotations

import sqlite3
from typing import Any

from slipform.domain.validation import normalize_datetime, optional_float

VALID_TRUCK_STATES = {"PLANIFICADA", "EN_TRANSITO", "EN_DESCARGA", "CONFIRMADA_EN_MOLDE", "LIBERADA"}


def create_descarga(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    row = conn.execute(
        """
        INSERT INTO descargas_olla(
            colado_id, numero_olla, volumen_m3, hora_salida_planta, hora_llegada_obra,
            hora_inicio_descarga, hora_fin_descarga, temperatura_salida_c,
            temperatura_llegada_c, revenimiento_cm, origen_generacion, estado_operativo, observaciones
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(payload["colado_id"]),
            str(payload.get("numero_olla") or "Olla 1"),
            optional_float(payload.get("volumen_m3")) or optional_float(payload.get("volumen_por_olla_m3")) or 5.0,
            _optional_datetime(payload.get("hora_salida_planta")),
            _optional_datetime(payload.get("hora_llegada_obra")),
            _optional_datetime(payload.get("hora_inicio_descarga")),
            _optional_datetime(payload.get("hora_fin_descarga")),
            optional_float(payload.get("temperatura_salida_c")),
            optional_float(payload.get("temperatura_llegada_c")),
            optional_float(payload.get("revenimiento_cm")),
            payload.get("origen_generacion") or "manual",
            _truck_state(payload),
            payload.get("observaciones"),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def get_descargas(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM descargas_olla WHERE colado_id = ? ORDER BY id",
            (colado_id,),
        ).fetchall()
    ]


def update_descarga(conn: sqlite3.Connection, descarga_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    existing = conn.execute("SELECT * FROM descargas_olla WHERE id = ?", (descarga_id,)).fetchone()
    if not existing:
        raise ValueError("Descarga/olla no encontrada.")
    conn.execute(
        """
        UPDATE descargas_olla
        SET numero_olla = ?,
            volumen_m3 = ?,
            hora_salida_planta = ?,
            hora_llegada_obra = ?,
            hora_inicio_descarga = ?,
            hora_fin_descarga = ?,
            temperatura_salida_c = ?,
            temperatura_llegada_c = ?,
            revenimiento_cm = ?,
            estado_operativo = ?,
            observaciones = ?
        WHERE id = ?
        """,
        (
            str(payload.get("numero_olla") or existing["numero_olla"]),
            optional_float(payload.get("volumen_m3")) or float(existing["volumen_m3"] or 5.0),
            _optional_datetime(payload.get("hora_salida_planta")),
            _optional_datetime(payload.get("hora_llegada_obra")),
            _optional_datetime(payload.get("hora_inicio_descarga")),
            _optional_datetime(payload.get("hora_fin_descarga")),
            optional_float(payload.get("temperatura_salida_c")),
            optional_float(payload.get("temperatura_llegada_c")),
            optional_float(payload.get("revenimiento_cm")),
            _truck_state(payload, existing["estado_operativo"] if "estado_operativo" in existing.keys() else None),
            payload.get("observaciones"),
            descarga_id,
        ),
    )
    plant_departure = _optional_datetime(payload.get("hora_salida_planta"))
    initial_temp = optional_float(payload.get("temperatura_llegada_c")) or optional_float(payload.get("temperatura_salida_c"))
    if plant_departure:
        conn.execute(
            """
            UPDATE zonas_colado
            SET hora_salida_planta = ?,
                hora_referencia_madurez = ?,
                volumen_m3 = ?,
                temperatura_inicial_c = COALESCE(?, temperatura_inicial_c)
            WHERE descarga_olla_id = ?
            """,
            (
                plant_departure,
                plant_departure,
                optional_float(payload.get("volumen_m3")) or float(existing["volumen_m3"] or 5.0),
                initial_temp,
                descarga_id,
            ),
        )
    elif initial_temp is not None:
        conn.execute(
            """
            UPDATE zonas_colado
            SET temperatura_inicial_c = ?
            WHERE descarga_olla_id = ?
            """,
            (initial_temp, descarga_id),
        )
    conn.commit()
    row = conn.execute("SELECT * FROM descargas_olla WHERE id = ?", (descarga_id,)).fetchone()
    return dict(row)


def _optional_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _optional_datetime(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return normalize_datetime(value, timespec="minutes")


def _truck_state(payload: dict[str, Any], fallback: str | None = None) -> str:
    raw = payload.get("estado_operativo") or fallback or "CONFIRMADA_EN_MOLDE"
    state = str(raw).strip().upper()
    if state not in VALID_TRUCK_STATES:
        raise ValueError(f"Estado operativo de olla invalido: {raw}.")
    return state


__all__ = ["VALID_TRUCK_STATES", "create_descarga", "get_descargas", "update_descarga"]
