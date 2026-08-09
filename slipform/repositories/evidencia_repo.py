"""Repository functions for field evidence: photos and plumb readings."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from slipform.domain.validation import normalize_datetime, optional_float


def insert_photo_evidence(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    row = conn.execute(
        """
        INSERT INTO fotografias_evidencia(
            colado_id, zona_colado_id, fecha_hora, elevacion_cm,
            descripcion, operador, imagen_data_url
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(payload["colado_id"]),
            _optional_int(payload.get("zona_colado_id")),
            normalize_datetime(payload.get("fecha_hora") or datetime.now().isoformat(timespec="seconds")),
            optional_float(payload.get("elevacion_cm")),
            payload.get("descripcion"),
            payload.get("operador"),
            payload.get("imagen_data_url"),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def list_photo_evidence(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT f.*, z.zona_numero
            FROM fotografias_evidencia f
            LEFT JOIN zonas_colado z ON z.id = f.zona_colado_id
            WHERE f.colado_id = ?
            ORDER BY f.fecha_hora DESC, f.id DESC
            """,
            (colado_id,),
        ).fetchall()
    ]


def insert_plumb_reading(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    tolerance = optional_float(payload.get("tolerancia_mm"))
    reading = float(payload["lectura_mm"])
    status = payload.get("estado")
    if not status:
        status = "FUERA_TOLERANCIA" if tolerance is not None and abs(reading) > abs(tolerance) else "OK"
    row = conn.execute(
        """
        INSERT INTO lecturas_desplome(
            colado_id, fecha_hora, punto, direccion, lectura_mm,
            tolerancia_mm, estado, operador, observaciones
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(payload["colado_id"]),
            normalize_datetime(payload.get("fecha_hora") or datetime.now().isoformat(timespec="seconds")),
            payload["punto"],
            payload["direccion"],
            reading,
            tolerance,
            status,
            payload.get("operador"),
            payload.get("observaciones"),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def insert_desplome(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    return insert_plumb_reading(conn, payload)


def list_plumb_readings(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM lecturas_desplome
            WHERE colado_id = ?
            ORDER BY fecha_hora DESC, id DESC
            """,
            (colado_id,),
        ).fetchall()
    ]


def list_desplomes(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    return list_plumb_readings(conn, colado_id)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


__all__ = [
    "insert_desplome",
    "insert_photo_evidence",
    "insert_plumb_reading",
    "list_desplomes",
    "list_photo_evidence",
    "list_plumb_readings",
]
