"""Handlers for JSON GET/query endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from slipform.domain.data_quality import build_data_quality_report
from slipform.db import (
    connect,
    get_active_advance_recipe,
    get_active_project,
    get_cylinder_test_schedule,
    get_descargas,
    get_events,
    get_sensor_health,
    get_zones,
    init_db,
    list_advance_recipes,
    list_bootstrap,
    list_model_adjustments,
    list_operational_alarms,
    list_photo_evidence,
    list_plumb_readings,
    list_shift_details,
)
from slipform.mold import calculate_mold_state
from slipform.scada import get_scada_state, get_trends


def handle_get(path: str, query: str, db_path: Path) -> tuple[int, dict[str, Any]] | None:
    params = parse_qs(query)

    if path == "/api/bootstrap":
        with connect(db_path) as conn:
            init_db(conn)
            return 200, list_bootstrap(conn)

    if path == "/api/eventos":
        colado_id = int(params.get("colado_id", ["0"])[0])
        with connect(db_path) as conn:
            init_db(conn)
            return 200, {"eventos": get_events(conn, colado_id)}

    if path == "/api/molde/estado":
        colado_id = int(params.get("colado_id", ["0"])[0])
        as_of = params.get("as_of", [None])[0]
        with connect(db_path) as conn:
            init_db(conn)
            return 200, calculate_mold_state(conn, colado_id, as_of_iso=as_of)

    if path == "/api/scada/estado":
        colado_id = int(params.get("colado_id", ["0"])[0])
        as_of = params.get("as_of", [None])[0]
        with connect(db_path) as conn:
            init_db(conn)
            return 200, get_scada_state(conn, colado_id, as_of_iso=as_of)

    if path == "/api/scada/alarmas":
        colado_id = int(params.get("colado_id", ["0"])[0])
        include_closed = params.get("include_closed", ["0"])[0] in ("1", "true", "si")
        with connect(db_path) as conn:
            init_db(conn)
            return 200, {"alarmas": list_operational_alarms(conn, colado_id, include_closed)}

    if path == "/api/tendencias":
        colado_id = int(params.get("colado_id", ["0"])[0])
        zone_raw = params.get("zona_id", [""])[0]
        zone_id = int(zone_raw) if zone_raw else None
        rango = params.get("rango", ["4h"])[0]
        as_of = params.get("as_of", [None])[0]
        with connect(db_path) as conn:
            init_db(conn)
            return 200, get_trends(conn, colado_id, zona_id=zone_id, rango=rango, as_of_iso=as_of)

    if path == "/api/receta-avance":
        colado_id = int(params.get("colado_id", ["0"])[0])
        with connect(db_path) as conn:
            init_db(conn)
            return 200, {
                "receta_activa": get_active_advance_recipe(conn, colado_id),
                "historial": list_advance_recipes(conn, colado_id),
            }

    if path == "/api/programa-deslizado":
        colado_id = int(params.get("colado_id", ["0"])[0])
        with connect(db_path) as conn:
            init_db(conn)
            return 200, get_cylinder_test_schedule(conn, colado_id)

    if path == "/api/calidad-datos":
        colado_id = int(params.get("colado_id", ["0"])[0])
        with connect(db_path) as conn:
            init_db(conn)
            return 200, {"calidad_datos": build_data_quality_report(conn, colado_id)}

    if path == "/api/proyecto":
        with connect(db_path) as conn:
            init_db(conn)
            return 200, {"proyecto": get_active_project(conn)}

    if path == "/api/zonas":
        colado_id = int(params.get("colado_id", ["0"])[0])
        with connect(db_path) as conn:
            init_db(conn)
            return 200, {"zonas": get_zones(conn, colado_id)}

    if path == "/api/descargas":
        colado_id = int(params.get("colado_id", ["0"])[0])
        with connect(db_path) as conn:
            init_db(conn)
            return 200, {"descargas": get_descargas(conn, colado_id)}

    if path == "/api/turnos":
        colado_id = int(params.get("colado_id", ["0"])[0])
        with connect(db_path) as conn:
            init_db(conn)
            return 200, {"turnos": list_shift_details(conn, colado_id)}

    if path == "/api/fotografias":
        colado_id = int(params.get("colado_id", ["0"])[0])
        with connect(db_path) as conn:
            init_db(conn)
            return 200, {"fotografias": list_photo_evidence(conn, colado_id)}

    if path == "/api/desplomes":
        colado_id = int(params.get("colado_id", ["0"])[0])
        with connect(db_path) as conn:
            init_db(conn)
            return 200, {"desplomes": list_plumb_readings(conn, colado_id)}

    if path == "/api/modelo/ajustes":
        colado_raw = params.get("colado_id", [""])[0]
        colado_id = int(colado_raw) if colado_raw else None
        with connect(db_path) as conn:
            init_db(conn)
            return 200, {"ajustes": list_model_adjustments(conn, colado_id)}

    if path == "/api/sensores/salud":
        colado_raw = params.get("colado_id", [""])[0]
        colado_id = int(colado_raw) if colado_raw else None
        with connect(db_path) as conn:
            init_db(conn)
            return 200, {"sensores": get_sensor_health(conn, colado_id)}

    return None


__all__ = ["handle_get"]
