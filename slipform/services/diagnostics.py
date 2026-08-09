"""Health and diagnostic summaries for the local SCADA."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from slipform.db import database_counts, get_schema_version
from slipform.services.backups import list_sqlite_backups


def service_worker_version(static_root: Path) -> str:
    sw_path = static_root / "sw.js"
    if not sw_path.exists():
        return "sin_service_worker"
    first_line = sw_path.read_text(encoding="utf-8").splitlines()[0]
    marker = "CACHE_NAME = "
    if marker not in first_line:
        return "desconocido"
    return first_line.split(marker, 1)[1].strip().strip(";").strip('"')


def health_report(conn, db_path: Path, static_root: Path) -> dict[str, Any]:
    db_path = Path(db_path)
    backups = list_sqlite_backups(db_path)
    return {
        "ok": True,
        "server_time": datetime.now().isoformat(timespec="seconds"),
        "sqlite": {
            "path": str(db_path),
            "exists": db_path.exists(),
            "bytes": db_path.stat().st_size if db_path.exists() else 0,
            "schema": get_schema_version(conn),
            "counts": database_counts(conn),
        },
        "backups": {
            "total": len(backups),
            "ultimo": backups[0] if backups else None,
        },
        "frontend": {
            "service_worker": service_worker_version(static_root),
        },
    }


__all__ = ["health_report", "service_worker_version"]
