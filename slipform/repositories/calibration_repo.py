"""Repository functions for model adjustments and generated report log."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from slipform.domain.validation import optional_float


def insert_model_adjustment(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    if not payload.get("justificacion"):
        raise ValueError("El ajuste requiere justificacion.")
    row = conn.execute(
        """
        INSERT INTO ajustes_modelo(
            mezcla_id, colado_id, fecha_hora, madurez_objetivo_h_eq,
            umbral_prepararse, umbral_deslizar, umbral_sobremadurez,
            tolerancia_velocidad_min_cm_h, tolerancia_velocidad_max_cm_h,
            operador, supervisor, justificacion
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            _optional_int(payload.get("mezcla_id")),
            _optional_int(payload.get("colado_id")),
            payload.get("fecha_hora") or datetime.now().isoformat(timespec="seconds"),
            optional_float(payload.get("madurez_objetivo_h_eq")),
            optional_float(payload.get("umbral_prepararse")),
            optional_float(payload.get("umbral_deslizar")),
            optional_float(payload.get("umbral_sobremadurez")),
            optional_float(payload.get("tolerancia_velocidad_min_cm_h")),
            optional_float(payload.get("tolerancia_velocidad_max_cm_h")),
            payload.get("operador"),
            payload.get("supervisor"),
            payload["justificacion"],
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def list_model_adjustments(conn: sqlite3.Connection, colado_id: int | None = None) -> list[dict[str, Any]]:
    if colado_id:
        params: tuple[Any, ...] = (colado_id,)
        where = "WHERE a.colado_id = ? OR a.colado_id IS NULL"
    else:
        params = ()
        where = ""
    return [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT a.*, m.nombre AS mezcla_nombre
            FROM ajustes_modelo a
            LEFT JOIN mezclas m ON m.id = a.mezcla_id
            {where}
            ORDER BY a.fecha_hora DESC, a.id DESC
            """,
            params,
        ).fetchall()
    ]


def insert_generated_report(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    row = conn.execute(
        """
        INSERT INTO reportes_generados(colado_id, tipo, fecha_hora, resumen_json)
        VALUES (?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(payload["colado_id"]),
            payload.get("tipo") or "CONTROL_CENTRAL",
            payload.get("fecha_hora") or datetime.now().isoformat(timespec="seconds"),
            json.dumps(payload.get("resumen") or {}, ensure_ascii=False),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


__all__ = ["insert_generated_report", "insert_model_adjustment", "list_model_adjustments"]
