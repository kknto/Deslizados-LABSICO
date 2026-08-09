"""Repository functions for schema diagnostics and operational audit."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from slipform.repositories.schema import init_db


def get_schema_version(conn: sqlite3.Connection) -> dict[str, Any]:
    init_db(conn)
    row = conn.execute(
        """
        SELECT version, applied_at, description
        FROM schema_migrations
        ORDER BY version DESC
        LIMIT 1
        """
    ).fetchone()
    return dict(row) if row else {"version": 0, "applied_at": None, "description": "sin_version"}


def database_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [
        "colados",
        "lecturas",
        "zonas_colado",
        "avances_molde",
        "eventos_deslizamiento",
        "alarmas_operativas",
        "decisiones_operador",
        "fotografias_evidencia",
        "lecturas_desplome",
        "mezclas",
        "curvas_laboratorio",
        "curvas_laboratorio_puntos",
    ]
    counts: dict[str, int] = {}
    for table in tables:
        counts[table] = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])
    return counts


def insert_audit(
    conn: sqlite3.Connection,
    action: str,
    entity: str,
    entity_id: int | None = None,
    colado_id: int | None = None,
    operator: str | None = None,
    reason: str | None = None,
    detail: dict[str, Any] | None = None,
) -> int:
    row = conn.execute(
        """
        INSERT INTO auditoria_operativa(
            fecha_hora, accion, entidad, entidad_id, colado_id, operador, motivo, detalle_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            action,
            entity,
            entity_id,
            colado_id,
            operator,
            reason,
            json.dumps(detail or {}, ensure_ascii=False),
        ),
    ).fetchone()
    return int(row["id"])


def list_audit(conn: sqlite3.Connection, limit: int = 100) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM auditoria_operativa
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    ]


def delete_demo_data(conn: sqlite3.Connection, operator: str | None = None, reason: str | None = None) -> dict[str, Any]:
    demo_rows = conn.execute("SELECT id FROM colados WHERE es_demo = 1 ORDER BY id").fetchall()
    demo_ids = [int(row["id"]) for row in demo_rows]
    if demo_ids:
        conn.executemany("DELETE FROM colados WHERE id = ?", [(item_id,) for item_id in demo_ids])
    insert_audit(
        conn,
        "DELETE_DEMO_DATA",
        "colados",
        operator=operator,
        reason=reason or "reset demo",
        detail={"colados_eliminados": demo_ids},
    )
    conn.commit()
    return {"colados_eliminados": demo_ids, "total": len(demo_ids)}


__all__ = ["database_counts", "delete_demo_data", "get_schema_version", "insert_audit", "list_audit"]
