"""Repository functions for slide events and prediction history."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from slipform.domain.validation import normalize_datetime, optional_float
from slipform.repositories.colados_repo import get_colado
from slipform.repositories.lecturas_repo import resolve_elapsed_minute


def insert_prediction(conn: sqlite3.Connection, colado_id: int, prediction: dict[str, Any]) -> int:
    row = conn.execute(
        """
        INSERT INTO predicciones(
            colado_id, fecha_hora, madurez_acumulada_h_eq, avance, estado,
            minutos_restantes, desviacion_vs_laboratorio, alertas_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            colado_id,
            datetime.now().isoformat(timespec="seconds"),
            prediction["madurez_acumulada_h_eq"],
            prediction["avance"],
            prediction["estado"],
            prediction["minutos_estimados_restantes"],
            prediction["desviacion_vs_laboratorio"],
            json.dumps(prediction["alertas"], ensure_ascii=False),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def insert_slide_event(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    _ensure_existing_colado(conn, int(payload["colado_id"]))
    if payload.get("decision_tomada") == "DESLIZAR" and not _slide_checklist_ok(payload):
        raise ValueError("Para registrar DESLIZAR se requiere confirmar el checklist fisico completo.")
    fecha_hora = normalize_datetime(payload.get("fecha_hora") or datetime.now().isoformat(timespec="seconds"))
    minute = resolve_elapsed_minute(conn, int(payload["colado_id"]), fecha_hora, payload.get("minuto_transcurrido"))
    row = conn.execute(
        """
        INSERT INTO eventos_deslizamiento(
            colado_id, fecha_hora, minuto_transcurrido, velocidad_deslizamiento_cm_h,
            decision_tomada, resultado_fisico,
            checklist_no_desmorona, checklist_no_se_pega,
            checklist_acabado_aceptable, checklist_sin_arrastre,
            observacion, supervisor
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(payload["colado_id"]),
            fecha_hora,
            minute,
            optional_float(payload.get("velocidad_deslizamiento_cm_h")),
            payload["decision_tomada"],
            payload["resultado_fisico"],
            _bool_int(payload.get("checklist_no_desmorona")),
            _bool_int(payload.get("checklist_no_se_pega")),
            _bool_int(payload.get("checklist_acabado_aceptable")),
            _bool_int(payload.get("checklist_sin_arrastre")),
            payload.get("observacion"),
            payload.get("supervisor"),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def get_events(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM eventos_deslizamiento
            WHERE colado_id = ?
            ORDER BY minuto_transcurrido, id
            """,
            (colado_id,),
        ).fetchall()
    ]


def _ensure_existing_colado(conn: sqlite3.Connection, colado_id: int) -> dict[str, Any]:
    colado = get_colado(conn, colado_id)
    if not colado:
        raise ValueError("Colado no encontrado.")
    if str(colado.get("estado") or "").upper() == "CANCELADO":
        raise ValueError("El colado esta cancelado.")
    return colado


def _slide_checklist_ok(payload: dict[str, Any]) -> bool:
    return all(
        _bool_int(payload.get(key))
        for key in [
            "checklist_no_desmorona",
            "checklist_no_se_pega",
            "checklist_acabado_aceptable",
            "checklist_sin_arrastre",
        ]
    )


def _bool_int(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if value in (None, ""):
        return 0
    if isinstance(value, str):
        return 1 if value.lower() in ("1", "true", "on", "yes", "si", "sí") else 0
    return 1 if value else 0


__all__ = ["get_events", "insert_prediction", "insert_slide_event"]
