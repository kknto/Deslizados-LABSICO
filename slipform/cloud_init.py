"""Inicializacion idempotente para despliegues web."""

from __future__ import annotations

import os
from pathlib import Path

from slipform.importer import import_curves
from slipform.repositories.connection import connect, database_engine
from slipform.repositories.schema import init_db

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "slipform.sqlite"
DEFAULT_CURVES_PATH = ROOT / "Curvas HRP.xlsx"


def resolve_db_path() -> Path:
    return Path(os.environ.get("SLIPFORM_DB_PATH") or DEFAULT_DB_PATH)


def initialize_database(db_path: str | Path | None = None, curves_path: str | Path | None = None) -> dict[str, int | str]:
    target_db = Path(db_path) if db_path is not None else resolve_db_path()
    target_curves = Path(curves_path) if curves_path is not None else DEFAULT_CURVES_PATH

    with connect(target_db) as conn:
        init_db(conn)
        curve_count = int(conn.execute("SELECT COUNT(*) FROM curvas_laboratorio").fetchone()[0])
        project_count = int(conn.execute("SELECT COUNT(*) FROM proyectos").fetchone()[0])

    imported_curves = 0
    if curve_count == 0 and target_curves.exists():
        imported_curves = import_curves(target_curves, target_db)

    with connect(target_db) as conn:
        init_db(conn)
        curve_count = int(conn.execute("SELECT COUNT(*) FROM curvas_laboratorio").fetchone()[0])
        project_count = int(conn.execute("SELECT COUNT(*) FROM proyectos").fetchone()[0])

    return {
        "db_path": str(target_db),
        "engine": database_engine(),
        "curves_path": str(target_curves),
        "imported_curves": imported_curves,
        "curve_count": curve_count,
        "project_count": project_count,
    }


def main() -> None:
    result = initialize_database()
    print("Inicializacion cloud completa")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
