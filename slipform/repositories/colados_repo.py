"""Repository functions for colados."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from slipform.domain.validation import normalize_datetime, validate_colado_payload
from slipform.repositories.audit_repo import insert_audit
from slipform.repositories.project_repo import get_active_project


def create_colado(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    validate_colado_payload(payload)
    fecha_hora_inicio = _resolve_start_time(payload)
    project_id = _optional_int(payload.get("proyecto_id"))
    if project_id is None:
        project_id = int(get_active_project(conn)["id"])
    row = conn.execute(
        """
        INSERT INTO colados(
            proyecto_id, silo_id, mezcla_id, curva_id, fecha_hora_inicio,
            hora_salida_planta, hora_llegada_obra, hora_inicio_descarga,
            hora_colocacion_en_molde, hora_fin_descarga, fecha_cierre,
            operador, estado, es_demo, observaciones
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVO', ?, ?)
        RETURNING id
        """,
        (
            project_id,
            payload["silo_id"],
            int(payload["mezcla_id"]),
            _optional_int(payload.get("curva_id")),
            fecha_hora_inicio,
            _normalize_optional_datetime(payload.get("hora_salida_planta")),
            _normalize_optional_datetime(payload.get("hora_llegada_obra")),
            _normalize_optional_datetime(payload.get("hora_inicio_descarga")),
            _normalize_optional_datetime(payload.get("hora_colocacion_en_molde")),
            _normalize_optional_datetime(payload.get("hora_fin_descarga")),
            _normalize_optional_datetime(payload.get("fecha_cierre")),
            payload.get("operador"),
            _bool_int(payload.get("es_demo")),
            payload.get("observaciones"),
        ),
    ).fetchone()
    item_id = int(row["id"])
    insert_audit(
        conn,
        "CREATE",
        "colados",
        entity_id=item_id,
        colado_id=item_id,
        operator=payload.get("operador"),
        detail={"silo_id": payload.get("silo_id"), "es_demo": bool(_bool_int(payload.get("es_demo")))},
    )
    conn.commit()
    return item_id


def update_colado(conn: sqlite3.Connection, colado_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_colado(conn, colado_id)
    if not existing:
        raise ValueError("Colado no encontrado.")
    validate_colado_payload(payload)
    fecha_hora_inicio = (
        payload.get("fecha_hora_inicio")
        or payload.get("hora_colocacion_en_molde")
        or payload.get("hora_inicio_descarga")
        or existing["fecha_hora_inicio"]
    )
    mezcla_id = int(payload["mezcla_id"])
    curva_id = _optional_int(payload.get("curva_id"))
    previous_state = str(existing.get("estado") or "ACTIVO").upper()
    next_state = str(payload.get("estado") or existing.get("estado") or "ACTIVO").upper()
    closing_time = _resolve_closing_time(payload, existing, next_state)
    conn.execute(
        """
        UPDATE colados
        SET silo_id = ?,
            mezcla_id = ?,
            curva_id = ?,
            fecha_hora_inicio = ?,
            hora_salida_planta = ?,
            hora_llegada_obra = ?,
            hora_inicio_descarga = ?,
            hora_colocacion_en_molde = ?,
            hora_fin_descarga = ?,
            fecha_cierre = ?,
            operador = ?,
            estado = ?,
            es_demo = ?,
            observaciones = ?
        WHERE id = ?
        """,
        (
            payload["silo_id"],
            mezcla_id,
            curva_id,
            fecha_hora_inicio,
            _datetime_from_payload_or_existing(payload, existing, "hora_salida_planta"),
            _datetime_from_payload_or_existing(payload, existing, "hora_llegada_obra"),
            _datetime_from_payload_or_existing(payload, existing, "hora_inicio_descarga"),
            _datetime_from_payload_or_existing(payload, existing, "hora_colocacion_en_molde"),
            _datetime_from_payload_or_existing(payload, existing, "hora_fin_descarga"),
            closing_time,
            payload.get("operador"),
            next_state,
            _bool_int(payload.get("es_demo", existing.get("es_demo"))),
            payload.get("observaciones"),
            colado_id,
        ),
    )
    conn.execute(
        """
        UPDATE zonas_colado
        SET mezcla_id = ?, curva_id = ?
        WHERE colado_id = ?
        """,
        (mezcla_id, curva_id, colado_id),
    )
    insert_audit(
        conn,
        "UPDATE",
        "colados",
        entity_id=colado_id,
        colado_id=colado_id,
        operator=payload.get("operador"),
        detail={"estado": payload.get("estado") or existing.get("estado")},
    )
    if previous_state != next_state or (existing.get("fecha_cierre") or None) != (closing_time or None):
        insert_audit(
            conn,
            "CLOSE_COLADO" if next_state == "CERRADO" else "CHANGE_COLADO_STATUS",
            "colados",
            entity_id=colado_id,
            colado_id=colado_id,
            operator=payload.get("operador"),
            reason=payload.get("motivo_cierre") or payload.get("observaciones") or "Cambio de estado del colado.",
            detail={
                "estado_anterior": previous_state,
                "estado_nuevo": next_state,
                "fecha_cierre_anterior": existing.get("fecha_cierre"),
                "fecha_cierre_nueva": closing_time,
            },
        )
    conn.commit()
    updated = get_colado(conn, colado_id)
    if not updated:
        raise ValueError("Colado no encontrado despues de actualizar.")
    return updated


def delete_colado(conn: sqlite3.Connection, colado_id: int) -> None:
    existing = get_colado(conn, colado_id)
    if not existing:
        raise ValueError("Colado no encontrado.")
    insert_audit(
        conn,
        "DELETE",
        "colados",
        entity_id=colado_id,
        colado_id=colado_id,
        operator=existing.get("operador"),
        detail={"silo_id": existing.get("silo_id"), "es_demo": existing.get("es_demo")},
    )
    conn.execute("DELETE FROM colados WHERE id = ?", (colado_id,))
    conn.commit()


def get_colado(conn: sqlite3.Connection, colado_id: int) -> dict[str, Any] | None:
    return _row_to_dict(
        conn.execute(
            """
            SELECT c.*, cl.parametros_json
            FROM colados c
            LEFT JOIN curvas_laboratorio cl ON cl.id = c.curva_id
            WHERE c.id = ?
            """,
            (colado_id,),
        ).fetchone()
    )


def list_colados(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT c.*, m.nombre AS mezcla_nombre, cl.nombre_curva
            FROM colados c
            JOIN mezclas m ON m.id = c.mezcla_id
            LEFT JOIN curvas_laboratorio cl ON cl.id = c.curva_id
            ORDER BY c.id DESC
            """
        ).fetchall()
    ]


def upsert_colado(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    return create_colado(conn, payload)


def _resolve_start_time(payload: dict[str, Any]) -> str:
    return normalize_datetime(
        payload.get("fecha_hora_inicio")
        or payload.get("hora_colocacion_en_molde")
        or payload.get("hora_inicio_descarga")
        or datetime.now().isoformat(timespec="minutes"),
        timespec="minutes",
    )


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    if result.get("parametros_json"):
        result["parametros"] = json.loads(result["parametros_json"])
    return result


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _normalize_optional_datetime(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return normalize_datetime(value, timespec="minutes")


def _datetime_from_payload_or_existing(payload: dict[str, Any], existing: dict[str, Any], key: str) -> str | None:
    if key not in payload:
        return existing.get(key)
    return _normalize_optional_datetime(payload.get(key))


def _resolve_closing_time(payload: dict[str, Any], existing: dict[str, Any], next_state: str) -> str | None:
    if next_state != "CERRADO":
        return _normalize_optional_datetime(payload.get("fecha_cierre")) if "fecha_cierre" in payload else None
    raw = payload.get("fecha_cierre") if "fecha_cierre" in payload else existing.get("fecha_cierre")
    if not raw:
        raise ValueError("Captura la fecha de cierre para marcar el colado como CERRADO.")
    closing_time = _normalize_optional_datetime(raw)
    start = (
        payload.get("fecha_hora_inicio")
        or payload.get("hora_colocacion_en_molde")
        or payload.get("hora_inicio_descarga")
        or existing.get("fecha_hora_inicio")
    )
    if start and closing_time and normalize_datetime(closing_time, timespec="minutes") < normalize_datetime(start, timespec="minutes"):
        raise ValueError("La fecha de cierre no puede ser anterior al inicio operativo del colado.")
    return closing_time


def _bool_int(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if value in (None, ""):
        return 0
    if isinstance(value, str):
        return 1 if value.lower() in ("1", "true", "si", "sí", "yes", "on") else 0
    return 1 if value else 0


__all__ = [
    "create_colado",
    "delete_colado",
    "get_colado",
    "list_colados",
    "update_colado",
    "upsert_colado",
]
