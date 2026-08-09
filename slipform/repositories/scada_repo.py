"""Repository functions for SCADA alarms, operator decisions and shifts."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from slipform.domain.validation import normalize_datetime, optional_float


def list_operational_alarms(
    conn: sqlite3.Connection,
    colado_id: int,
    include_closed: bool = False,
) -> list[dict[str, Any]]:
    where = "colado_id = ?"
    params: list[Any] = [colado_id]
    if not include_closed:
        where += " AND estado != 'CERRADA'"
    return [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT *
            FROM alarmas_operativas
            WHERE {where}
            ORDER BY
              CASE severidad
                WHEN 'CRITICA' THEN 1
                WHEN 'ALTA' THEN 2
                WHEN 'MEDIA' THEN 3
                ELSE 4
              END,
              fecha_hora_inicio DESC,
              id DESC
            """,
            params,
        ).fetchall()
    ]


def list_alarms(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    return list_operational_alarms(conn, colado_id, include_closed=True)


def upsert_operational_alarm(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    now = normalize_datetime(payload.get("fecha_hora_inicio") or datetime.now().isoformat(timespec="seconds"))
    colado_id = int(payload["colado_id"])
    zone_id = _optional_int(payload.get("zona_colado_id"))
    tipo = str(payload["tipo"])
    existing = conn.execute(
        """
        SELECT id
        FROM alarmas_operativas
        WHERE colado_id = ?
          AND COALESCE(zona_colado_id, 0) = COALESCE(?, 0)
          AND tipo = ?
          AND estado != 'CERRADA'
        ORDER BY id DESC
        LIMIT 1
        """,
        (colado_id, zone_id, tipo),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE alarmas_operativas
            SET severidad = ?, mensaje = ?
            WHERE id = ?
            """,
            (payload.get("severidad") or "MEDIA", payload.get("mensaje") or tipo, int(existing["id"])),
        )
        conn.commit()
        return int(existing["id"])
    row = conn.execute(
        """
        INSERT INTO alarmas_operativas(
            colado_id, zona_colado_id, tipo, severidad, estado,
            fecha_hora_inicio, mensaje
        )
        VALUES (?, ?, ?, ?, 'ACTIVA', ?, ?)
        RETURNING id
        """,
        (
            colado_id,
            zone_id,
            tipo,
            payload.get("severidad") or "MEDIA",
            now,
            payload.get("mensaje") or tipo,
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def upsert_alarm(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    return upsert_operational_alarm(conn, payload)


def close_stale_operational_alarms(
    conn: sqlite3.Connection,
    colado_id: int,
    active_keys: set[tuple[int | None, str]],
    fecha_hora: str | None = None,
) -> int:
    now = normalize_datetime(fecha_hora or datetime.now().isoformat(timespec="seconds"))
    open_rows = conn.execute(
        """
        SELECT id, zona_colado_id, tipo
        FROM alarmas_operativas
        WHERE colado_id = ? AND estado != 'CERRADA'
        """,
        (colado_id,),
    ).fetchall()
    closed = 0
    for row in open_rows:
        key = (int(row["zona_colado_id"]) if row["zona_colado_id"] is not None else None, str(row["tipo"]))
        if key not in active_keys:
            conn.execute(
                """
                UPDATE alarmas_operativas
                SET estado = 'CERRADA', fecha_hora_cierre = ?
                WHERE id = ?
                """,
                (now, int(row["id"])),
            )
            closed += 1
    conn.commit()
    return closed


def acknowledge_operational_alarm(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    alarm_id = int(payload["id"])
    now = normalize_datetime(payload.get("fecha_hora_reconocimiento") or datetime.now().isoformat(timespec="seconds"))
    conn.execute(
        """
        UPDATE alarmas_operativas
        SET estado = CASE WHEN estado = 'CERRADA' THEN estado ELSE 'RECONOCIDA' END,
            fecha_hora_reconocimiento = COALESCE(fecha_hora_reconocimiento, ?),
            operador_reconoce = ?
        WHERE id = ?
        """,
        (now, payload.get("operador_reconoce") or payload.get("operador"), alarm_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM alarmas_operativas WHERE id = ?", (alarm_id,)).fetchone()
    if row is None:
        raise ValueError("Alarma no encontrada.")
    return dict(row)


def acknowledge_alarm(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    return acknowledge_operational_alarm(conn, payload)


def insert_operator_decision(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    row = conn.execute(
        """
        INSERT INTO decisiones_operador(
            colado_id, zona_colado_id, avance_molde_id, fecha_hora,
            recomendacion_sistema, decision_operador, conforme_recomendacion, requiere_supervisor,
            operador, supervisor, checklist_json, observacion
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(payload["colado_id"]),
            _optional_int(payload.get("zona_colado_id")),
            _optional_int(payload.get("avance_molde_id")),
            normalize_datetime(payload.get("fecha_hora") or datetime.now().isoformat(timespec="seconds")),
            payload.get("recomendacion_sistema") or "SIN_DATOS",
            payload.get("decision_operador") or "SIN_DECISION",
            _bool_int(payload.get("conforme_recomendacion", 1)),
            _bool_int(payload.get("requiere_supervisor")),
            payload.get("operador"),
            payload.get("supervisor"),
            json.dumps(payload.get("checklist") or payload.get("checklist_json") or {}, ensure_ascii=False),
            payload.get("observacion"),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def list_operator_decisions(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM decisiones_operador
            WHERE colado_id = ?
            ORDER BY fecha_hora DESC, id DESC
            """,
            (colado_id,),
        ).fetchall()
    ]
    for row in rows:
        if row.get("checklist_json"):
            row["checklist"] = json.loads(row["checklist_json"])
    return rows


def list_decisions(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    return list_operator_decisions(conn, colado_id)


def insert_field_release(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    checklist = payload.get("checklist") or payload.get("checklist_json") or {}
    if not _checklist_complete(checklist):
        raise ValueError("La liberacion por criterio requiere checklist fisico completo.")
    if optional_float(payload.get("temperatura_concreto_c")) is None:
        raise ValueError("La liberacion por criterio requiere temperatura del concreto.")
    if not str(payload.get("condicion_observada") or "").strip():
        raise ValueError("La liberacion por criterio requiere condicion observada.")
    if not str(payload.get("motivo") or "").strip():
        raise ValueError("La liberacion por criterio requiere motivo.")
    if not str(payload.get("supervisor") or "").strip():
        raise ValueError("La liberacion por criterio requiere supervisor.")

    zone_id = int(payload["zona_colado_id"])
    conn.execute(
        """
        UPDATE liberaciones_campo
        SET activo = 0
        WHERE zona_colado_id = ? AND activo = 1
        """,
        (zone_id,),
    )
    row = conn.execute(
        """
        INSERT INTO liberaciones_campo(
            colado_id, zona_colado_id, fecha_hora,
            madurez_calculada_pct, madurez_operativa_pct,
            temperatura_concreto_c, temperatura_ambiente_c, humedad_relativa_pct,
            condicion_observada, checklist_json, motivo,
            operador, supervisor, activo
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        RETURNING id
        """,
        (
            int(payload["colado_id"]),
            zone_id,
            normalize_datetime(payload.get("fecha_hora") or datetime.now().isoformat(timespec="seconds")),
            float(payload.get("madurez_calculada_pct") or 0.0),
            float(payload.get("madurez_operativa_pct") or 90.0),
            float(payload["temperatura_concreto_c"]),
            optional_float(payload.get("temperatura_ambiente_c")),
            optional_float(payload.get("humedad_relativa_pct")),
            str(payload["condicion_observada"]).strip(),
            json.dumps(checklist, ensure_ascii=False),
            str(payload["motivo"]).strip(),
            payload.get("operador"),
            str(payload["supervisor"]).strip(),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def latest_active_field_release(conn: sqlite3.Connection, zona_colado_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM liberaciones_campo
        WHERE zona_colado_id = ? AND activo = 1
        ORDER BY fecha_hora DESC, id DESC
        LIMIT 1
        """,
        (int(zona_colado_id),),
    ).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["checklist"] = json.loads(item.get("checklist_json") or "{}")
    return item


def list_field_releases(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT lc.*, z.zona_numero
            FROM liberaciones_campo lc
            LEFT JOIN zonas_colado z ON z.id = lc.zona_colado_id
            WHERE lc.colado_id = ?
            ORDER BY lc.fecha_hora DESC, lc.id DESC
            """,
            (int(colado_id),),
        ).fetchall()
    ]
    for row in rows:
        row["checklist"] = json.loads(row.get("checklist_json") or "{}")
    return rows


def upsert_field_prediction_adjustment(conn: sqlite3.Connection, payload: dict[str, Any]) -> int | None:
    zone_id = int(payload["zona_base_id"])
    zone = conn.execute("SELECT * FROM zonas_colado WHERE id = ?", (zone_id,)).fetchone()
    if zone is None:
        raise ValueError("Zona base no encontrada.")
    plant_departure = zone["hora_salida_planta"] or zone["hora_referencia_madurez"]
    if not plant_departure:
        return None
    release_time = normalize_datetime(payload.get("fecha_hora") or datetime.now().isoformat(timespec="seconds"))
    departure_time = normalize_datetime(plant_departure)
    age_h = (datetime.fromisoformat(release_time) - datetime.fromisoformat(departure_time)).total_seconds() / 3600.0
    if age_h <= 0:
        return None
    colado_id = int(payload["colado_id"])
    conn.execute(
        """
        UPDATE ajustes_prediccion_campo
        SET activo = 0
        WHERE colado_id = ? AND activo = 1
        """,
        (colado_id,),
    )
    row = conn.execute(
        """
        INSERT INTO ajustes_prediccion_campo(
            colado_id, zona_base_id, fecha_hora, hora_salida_planta_zona_base,
            edad_observada_liberacion_h, madurez_calculada_pct, temperatura_concreto_c,
            motivo, operador, supervisor, activo
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        RETURNING id
        """,
        (
            colado_id,
            zone_id,
            release_time,
            departure_time,
            round(age_h, 6),
            float(payload.get("madurez_calculada_pct") or 0.0),
            optional_float(payload.get("temperatura_concreto_c")),
            payload.get("motivo"),
            payload.get("operador"),
            payload.get("supervisor"),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def latest_field_prediction_adjustment(conn: sqlite3.Connection, colado_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT a.*, z.zona_numero AS zona_base_numero
        FROM ajustes_prediccion_campo a
        LEFT JOIN zonas_colado z ON z.id = a.zona_base_id
        WHERE a.colado_id = ? AND a.activo = 1
        ORDER BY a.fecha_hora DESC, a.id DESC
        LIMIT 1
        """,
        (int(colado_id),),
    ).fetchone()
    return dict(row) if row else None


def list_field_prediction_adjustments(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT a.*, z.zona_numero AS zona_base_numero
            FROM ajustes_prediccion_campo a
            LEFT JOIN zonas_colado z ON z.id = a.zona_base_id
            WHERE a.colado_id = ?
            ORDER BY a.fecha_hora DESC, a.id DESC
            """,
            (int(colado_id),),
        ).fetchall()
    ]


def insert_shift(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    row = conn.execute(
        """
        INSERT INTO turnos_operacion(colado_id, operador, inicio_turno, fin_turno)
        VALUES (?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(payload["colado_id"]),
            payload["operador"],
            normalize_datetime(payload.get("inicio_turno") or datetime.now().isoformat(timespec="seconds")),
            _normalize_optional_datetime(payload.get("fin_turno")),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def start_shift(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    return insert_shift(conn, payload)


def insert_shift_detail(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    row = conn.execute(
        """
        INSERT INTO turnos_operacion_detalle(
            colado_id, turno, operador, inicio_turno, fin_turno,
            nivel_fin_turno_m, avance_parcial_m, avance_acumulado_m,
            ritmo_cm_h, observaciones
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(payload["colado_id"]),
            payload.get("turno") or "1ro",
            payload.get("operador"),
            normalize_datetime(payload.get("inicio_turno") or datetime.now().isoformat(timespec="seconds")),
            _normalize_optional_datetime(payload.get("fin_turno")),
            optional_float(payload.get("nivel_fin_turno_m")),
            optional_float(payload.get("avance_parcial_m")),
            optional_float(payload.get("avance_acumulado_m")),
            optional_float(payload.get("ritmo_cm_h")),
            payload.get("observaciones"),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def close_shift_detail(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    shift_id = int(payload["id"])
    row = conn.execute("SELECT * FROM turnos_operacion_detalle WHERE id = ?", (shift_id,)).fetchone()
    if row is None:
        raise ValueError("Turno no encontrado.")
    conn.execute(
        """
        UPDATE turnos_operacion_detalle
        SET fin_turno = ?,
            nivel_fin_turno_m = ?,
            avance_parcial_m = ?,
            avance_acumulado_m = ?,
            ritmo_cm_h = ?,
            observaciones = ?
        WHERE id = ?
        """,
        (
            normalize_datetime(payload.get("fin_turno") or datetime.now().isoformat(timespec="seconds")),
            optional_float(payload.get("nivel_fin_turno_m")),
            optional_float(payload.get("avance_parcial_m")),
            optional_float(payload.get("avance_acumulado_m")),
            optional_float(payload.get("ritmo_cm_h")),
            payload.get("observaciones"),
            shift_id,
        ),
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM turnos_operacion_detalle WHERE id = ?", (shift_id,)).fetchone()
    return dict(updated)


def close_shift(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    return close_shift_detail(conn, payload)


def list_shift_details(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM turnos_operacion_detalle
            WHERE colado_id = ?
            ORDER BY inicio_turno DESC, id DESC
            """,
            (colado_id,),
        ).fetchall()
    ]


def get_active_shift(conn: sqlite3.Connection, colado_id: int) -> dict[str, Any] | None:
    for row in list_shift_details(conn, colado_id):
        if not row.get("fin_turno"):
            return row
    return None


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
    return normalize_datetime(value)


def _bool_int(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if value in (None, ""):
        return 0
    if isinstance(value, str):
        return 1 if value.lower() in ("1", "true", "on", "yes", "si", "sí") else 0
    return 1 if value else 0


def _checklist_complete(checklist: dict[str, Any]) -> bool:
    return all(
        bool(checklist.get(key))
        for key in ("no_desmorona", "no_se_pega", "acabado_aceptable", "sin_arrastre")
    )


__all__ = [
    "acknowledge_alarm",
    "acknowledge_operational_alarm",
    "close_shift",
    "close_shift_detail",
    "close_stale_operational_alarms",
    "get_active_shift",
    "insert_field_release",
    "insert_operator_decision",
    "insert_shift",
    "insert_shift_detail",
    "latest_active_field_release",
    "latest_field_prediction_adjustment",
    "list_field_prediction_adjustments",
    "list_field_releases",
    "list_alarms",
    "list_decisions",
    "list_operational_alarms",
    "list_operator_decisions",
    "list_shift_details",
    "start_shift",
    "upsert_field_prediction_adjustment",
    "upsert_alarm",
    "upsert_operational_alarm",
]
