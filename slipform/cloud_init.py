"""Inicializacion idempotente para despliegues web."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

from slipform.importer import import_curves
from slipform.repositories.connection import connect, database_engine
from slipform.repositories.schema import init_db

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "slipform.sqlite"
DEFAULT_CURVES_PATH = ROOT / "Curvas HRP.xlsx"


def resolve_db_path() -> Path:
    return Path(os.environ.get("SLIPFORM_DB_PATH") or DEFAULT_DB_PATH)


def initialize_database(
    db_path: str | Path | None = None,
    curves_path: str | Path | None = None,
    *,
    attempts: int = 12,
    delay_seconds: float = 5.0,
) -> dict[str, int | str]:
    target_db = Path(db_path) if db_path is not None else resolve_db_path()
    target_curves = Path(curves_path) if curves_path is not None else DEFAULT_CURVES_PATH

    def load_counts() -> tuple[int, int]:
        with connect(target_db) as conn:
            init_db(conn)
            curves = int(conn.execute("SELECT COUNT(*) FROM curvas_laboratorio").fetchone()[0])
            projects = int(conn.execute("SELECT COUNT(*) FROM proyectos").fetchone()[0])
            return curves, projects

    curve_count, project_count = _with_retries(load_counts, attempts=attempts, delay_seconds=delay_seconds)

    imported_curves = 0
    if curve_count == 0 and target_curves.exists():
        imported_curves = import_curves(target_curves, target_db)

    curve_count, project_count = _with_retries(load_counts, attempts=attempts, delay_seconds=delay_seconds)

    return {
        "db_path": str(target_db),
        "engine": database_engine(),
        "curves_path": str(target_curves),
        "imported_curves": imported_curves,
        "curve_count": curve_count,
        "project_count": project_count,
    }


def _with_retries(
    action: Callable[[], tuple[int, int]],
    *,
    attempts: int,
    delay_seconds: float,
) -> tuple[int, int]:
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return action()
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            print(
                f"Base no disponible para inicializar (intento {attempt}/{attempts}); "
                f"reintentando en {delay_seconds:g}s: {exc}"
            )
            time.sleep(delay_seconds)
    raise RuntimeError("No fue posible inicializar la base de datos.") from last_error


def main() -> None:
    result = initialize_database()
    print("Inicializacion cloud completa")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
