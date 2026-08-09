"""SQLite backup utilities for local field operation."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from slipform.repositories.connection import database_engine


def backup_dir_for(db_path: Path) -> Path:
    return db_path.parent / "backups"


def create_sqlite_backup(db_path: Path, reason: str = "manual") -> dict[str, Any]:
    if database_engine() == "postgres":
        return _postgres_backup_notice(reason)
    source_path = Path(db_path)
    if not source_path.exists():
        raise FileNotFoundError(f"No existe la base SQLite: {source_path}")
    backup_dir = backup_dir_for(source_path)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_reason = re.sub(r"[^a-zA-Z0-9_-]+", "_", reason or "manual").strip("_")[:40] or "manual"
    target = backup_dir / f"slipform_{safe_reason}_{stamp}.sqlite"
    source = sqlite3.connect(source_path)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return backup_info(target)


def backup_info(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "nombre": path.name,
        "ruta": str(path),
        "bytes": stat.st_size,
        "fecha_hora": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def list_sqlite_backups(db_path: Path) -> list[dict[str, Any]]:
    if database_engine() == "postgres":
        return []
    backup_dir = backup_dir_for(Path(db_path))
    if not backup_dir.exists():
        return []
    return sorted(
        (backup_info(path) for path in backup_dir.glob("*.sqlite")),
        key=lambda item: item["fecha_hora"],
        reverse=True,
    )


def _postgres_backup_notice(reason: str) -> dict[str, Any]:
    return {
        "tipo": "postgres_render",
        "motivo": reason,
        "disponible": False,
        "mensaje": "En PostgreSQL los respaldos de produccion se gestionan desde Render Postgres.",
    }


__all__ = ["backup_dir_for", "backup_info", "create_sqlite_backup", "list_sqlite_backups"]
