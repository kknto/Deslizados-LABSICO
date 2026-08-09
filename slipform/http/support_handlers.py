"""Handlers for support/diagnostic endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from slipform.db import (
    connect,
    delete_demo_data,
    get_schema_version,
    init_db,
    insert_reading,
    insert_zone_reading,
    list_audit,
)
from slipform.services.backups import create_sqlite_backup, list_sqlite_backups
from slipform.services.diagnostics import health_report


def get_health(db_path: Path, static_root: Path) -> dict[str, Any]:
    with connect(db_path) as conn:
        init_db(conn)
        return health_report(conn, db_path, static_root)


def get_schema(db_path: Path) -> dict[str, Any]:
    with connect(db_path) as conn:
        init_db(conn)
        return {"schema": get_schema_version(conn)}


def get_backups(db_path: Path) -> dict[str, Any]:
    return {"backups": list_sqlite_backups(db_path)}


def get_audit(db_path: Path, limit: int = 100) -> dict[str, Any]:
    with connect(db_path) as conn:
        init_db(conn)
        return {"auditoria": list_audit(conn, limit=limit)}


def create_backup(db_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return {"backup": create_sqlite_backup(db_path, str(payload.get("motivo") or "manual"))}


def reset_demo_data(db_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    backup = create_sqlite_backup(db_path, "before_demo_reset")
    with connect(db_path) as conn:
        init_db(conn)
        result = delete_demo_data(
            conn,
            operator=payload.get("operador"),
            reason=payload.get("motivo") or "reset demo",
        )
    return {"backup": backup, "resultado": result}


def ingest_sensor_reading(db_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    with connect(db_path) as conn:
        init_db(conn)
        payload["origen"] = payload.get("origen") or "sensor"
        if payload.get("zona_colado_id"):
            item_id = insert_zone_reading(conn, payload)
            return {"id": item_id, "tipo": "lectura_zona"}
        item_id = insert_reading(conn, payload)
        return {"id": item_id, "tipo": "lectura_colado"}


__all__ = [
    "create_backup",
    "get_backups",
    "get_audit",
    "get_health",
    "get_schema",
    "ingest_sensor_reading",
    "reset_demo_data",
]
