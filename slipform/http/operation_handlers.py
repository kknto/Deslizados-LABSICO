"""Handlers for mutating operational endpoints."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from slipform.domain.data_quality import require_timing_confirmation
from slipform.db import (
    acknowledge_operational_alarm,
    close_shift_detail,
    connect,
    create_colado,
    create_descarga,
    create_zone,
    delete_colado,
    ensure_continuous_zones,
    generate_zones,
    get_active_advance_recipe,
    get_active_project,
    get_advances,
    get_cylinder_test_schedule,
    get_colado,
    get_descargas,
    get_zones,
    get_zones_generated_by_advance,
    initialize_colado_start_offset,
    init_db,
    insert_audit,
    insert_model_adjustment,
    insert_mold_advance,
    insert_photo_evidence,
    insert_plumb_reading,
    insert_reading,
    insert_shift,
    insert_shift_detail,
    insert_slide_event,
    insert_zone_reading,
    register_truck_zone,
    simulate_curve_readings,
    simulate_operational_advances,
    save_cylinder_test_schedule,
    update_colado,
    update_descarga,
    upsert_advance_recipe,
    upsert_mold_config,
    upsert_project,
)
from slipform.mold import calculate_mold_state
from slipform.scada import confirm_scada_advance, release_zone_by_field_criteria
from slipform.services.backups import create_sqlite_backup
from slipform.services.written_log_import import (
    commit_written_log_import,
    ensure_written_log_templates,
    preview_written_log_import,
    project_root_for_db,
)
from slipform.services.written_log_ocr import automatic_written_log_preview


def handle_post(path: str, db_path: Path, payload: dict[str, Any]) -> tuple[int, dict[str, Any]] | None:
    if path == "/api/bitacora-escrita/plantillas":
        return 201, ensure_written_log_templates(project_root_for_db(db_path))

    if path == "/api/bitacora-escrita/preview":
        with connect(db_path) as conn:
            init_db(conn)
            payload["_project_root"] = str(project_root_for_db(db_path))
            result = preview_written_log_import(conn, payload)
        return 200, result

    if path == "/api/bitacora-escrita/ocr-preview":
        with connect(db_path) as conn:
            init_db(conn)
            payload["_project_root"] = str(project_root_for_db(db_path))
            result = automatic_written_log_preview(conn, payload)
        return 200, result

    if path == "/api/bitacora-escrita/importar":
        with connect(db_path) as conn:
            init_db(conn)
            if payload.get("colado_id") not in (None, ""):
                _ensure_colado_open_for_operation(conn, int(payload["colado_id"]))
            payload["_project_root"] = str(project_root_for_db(db_path))
            result = commit_written_log_import(conn, db_path, payload)
        return 201, result

    if path == "/api/colados":
        with connect(db_path) as conn:
            init_db(conn)
            item_id = create_colado(conn, payload)
        return 201, {"id": item_id}

    if _blocks_closed_colado(path) and payload.get("colado_id") not in (None, ""):
        with connect(db_path) as conn:
            init_db(conn)
            _ensure_colado_open_for_operation(conn, int(payload["colado_id"]))

    if path == "/api/proyecto":
        with connect(db_path) as conn:
            init_db(conn)
            item_id = upsert_project(conn, payload)
            project = get_active_project(conn)
        return 201, {"id": item_id, "proyecto": project}

    if path in ("/api/lecturas", "/api/sensor-readings"):
        with connect(db_path) as conn:
            init_db(conn)
            payload["origen"] = payload.get("origen") or ("sensor" if path != "/api/lecturas" else "manual")
            item_id = insert_reading(conn, payload)
        return 201, {"id": item_id, "tipo": "lectura_colado"}

    if path == "/api/eventos":
        with connect(db_path) as conn:
            init_db(conn)
            item_id = insert_slide_event(conn, payload)
        return 201, {"id": item_id}

    if path == "/api/molde/configuracion":
        with connect(db_path) as conn:
            init_db(conn)
            item_id = upsert_mold_config(conn, payload)
        return 201, {"id": item_id}

    if path == "/api/descargas":
        with connect(db_path) as conn:
            init_db(conn)
            warnings = require_timing_confirmation(
                payload,
                existing_loads=get_descargas(conn, int(payload["colado_id"])),
            )
            item_id = create_descarga(conn, payload)
            _audit_confirmed_quality_warnings(conn, payload, "CREATE_DESCARGA", "descargas_olla", item_id, warnings)
        return 201, {"id": item_id}

    if path == "/api/ollas/registrar-zona":
        with connect(db_path) as conn:
            init_db(conn)
            previous_load = conn.execute(
                """
                SELECT *
                FROM descargas_olla
                WHERE colado_id = ? AND CAST(numero_olla AS TEXT) = ?
                ORDER BY id
                LIMIT 1
                """,
                (int(payload["colado_id"]), str(payload.get("numero_olla") or "")),
            ).fetchone()
            warnings = require_timing_confirmation(
                payload,
                existing_loads=get_descargas(conn, int(payload["colado_id"])),
            )
            result = register_truck_zone(conn, payload)
            if previous_load:
                _audit_critical_correction(
                    conn,
                    payload,
                    "CORRECT_TRUCK_LOAD",
                    "descargas_olla",
                    result.get("descarga", {}).get("id"),
                    dict(previous_load),
                    result.get("descarga") or {},
                    "Recalculo de madurez de zona por correccion de olla.",
                )
            _audit_confirmed_quality_warnings(
                conn,
                payload,
                "REGISTER_TRUCK_ZONE_WITH_WARNINGS",
                "descargas_olla",
                result.get("descarga", {}).get("id"),
                warnings,
            )
            state = calculate_mold_state(conn, int(payload["colado_id"]))
        return 201, result | {"estado_molde": state}

    if path == "/api/colados/inicializar-arranque":
        with connect(db_path) as conn:
            init_db(conn)
            result = initialize_colado_start_offset(conn, payload)
            state = calculate_mold_state(conn, int(payload["colado_id"]))
        return 201, result | {"estado_molde": state}

    if path == "/api/zonas":
        with connect(db_path) as conn:
            init_db(conn)
            item_id = create_zone(conn, payload)
        return 201, {"id": item_id}

    if path == "/api/zonas/generar":
        with connect(db_path) as conn:
            init_db(conn)
            ids = generate_zones(conn, payload)
            zones = [zone for zone in get_zones(conn, int(payload["colado_id"])) if int(zone["id"]) in set(ids)]
        return 201, {"ids": ids, "zonas_generadas": len(ids), "zonas": zones}

    if path == "/api/zonas/asegurar-continuidad":
        with connect(db_path) as conn:
            init_db(conn)
            colado_id = int(payload["colado_id"])
            advances = get_advances(conn, colado_id)
            previous_advance = float(advances[-2]["avance_acumulado_cm"]) if len(advances) >= 2 else 0.0
            current_advance = float(advances[-1]["avance_acumulado_cm"]) if advances else 0.0
            current_time = str(payload.get("fecha_hora") or (advances[-1]["fecha_hora"] if advances else datetime.now().isoformat(timespec="seconds")))
            previous_time = str(advances[-2]["fecha_hora"]) if len(advances) >= 2 else None
            ids = ensure_continuous_zones(
                conn,
                colado_id,
                previous_advance,
                current_advance,
                current_time,
                previous_fecha_hora=previous_time,
                advance_id=int(advances[-1]["id"]) if advances else None,
            )
            state = calculate_mold_state(conn, colado_id)
        return 201, {"ids": ids, "zonas_generadas": len(ids), "estado_molde": state}

    if path == "/api/zonas/liberar-por-criterio":
        with connect(db_path) as conn:
            init_db(conn)
            result = release_zone_by_field_criteria(conn, payload)
        return 201, result

    if path == "/api/lecturas-zona":
        with connect(db_path) as conn:
            init_db(conn)
            item_id = insert_zone_reading(conn, payload)
        return 201, {"id": item_id}

    if path in ("/api/avances", "/api/avances/registrar-5min"):
        with connect(db_path) as conn:
            init_db(conn)
            item_id = insert_mold_advance(conn, payload)
            created_zones = get_zones_generated_by_advance(conn, item_id)
            state = calculate_mold_state(conn, int(payload["colado_id"]))
        return 201, {"id": item_id, "zonas_creadas": created_zones, "estado_molde": state}

    if path == "/api/scada/confirmar-avance":
        with connect(db_path) as conn:
            init_db(conn)
            result = confirm_scada_advance(conn, payload)
            created_zones = get_zones_generated_by_advance(conn, result["avance_molde_id"]) if result.get("avance_molde_id") else []
        return 201, result | {"zonas_creadas": created_zones}

    if path == "/api/scada/alarmas/reconocer":
        with connect(db_path) as conn:
            init_db(conn)
            alarm = acknowledge_operational_alarm(conn, payload)
        return 200, {"alarma": alarm}

    if path == "/api/turnos":
        with connect(db_path) as conn:
            init_db(conn)
            item_id = insert_shift_detail(conn, payload) if payload.get("turno") else insert_shift(conn, payload)
        return 201, {"id": item_id}

    if path == "/api/turnos/cerrar":
        with connect(db_path) as conn:
            init_db(conn)
            turno = close_shift_detail(conn, payload)
        return 200, {"turno": turno}

    if path == "/api/fotografias":
        with connect(db_path) as conn:
            init_db(conn)
            item_id = insert_photo_evidence(conn, payload)
        return 201, {"id": item_id}

    if path == "/api/desplomes":
        with connect(db_path) as conn:
            init_db(conn)
            item_id = insert_plumb_reading(conn, payload)
        return 201, {"id": item_id}

    if path == "/api/modelo/ajustes":
        with connect(db_path) as conn:
            init_db(conn)
            item_id = insert_model_adjustment(conn, payload)
        return 201, {"id": item_id}

    if path == "/api/receta-avance":
        with connect(db_path) as conn:
            init_db(conn)
            item_id = upsert_advance_recipe(conn, payload)
            recipe = get_active_advance_recipe(conn, int(payload["colado_id"]))
        return 201, {"id": item_id, "receta_activa": recipe}

    if path in ("/api/programa-deslizado", "/api/programa-deslizado/ensayo"):
        with connect(db_path) as conn:
            init_db(conn)
            previous_revision = conn.execute(
                """
                SELECT *
                FROM ensayos_cilindro_deslizamiento
                WHERE colado_id = ? AND start_zone = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (int(payload["colado_id"]), int(payload.get("start_zone") or payload.get("zona_inicial") or 1)),
            ).fetchone()
            warnings = require_timing_confirmation({**payload, "hora_salida_planta": payload.get("t_fabricacion") or payload.get("hora_salida_planta")})
            result = save_cylinder_test_schedule(conn, payload)
            if previous_revision and isinstance(result.get("ensayo"), dict):
                _audit_critical_correction(
                    conn,
                    payload,
                    "CORRECT_CYLINDER_TEST",
                    "ensayos_cilindro_deslizamiento",
                    result["ensayo"].get("id"),
                    dict(previous_revision),
                    result["ensayo"],
                    "Recalculo de programa de deslizado por correccion de cilindro.",
                )
            _audit_confirmed_quality_warnings(
                conn,
                payload,
                "SAVE_CYLINDER_TEST_WITH_WARNINGS",
                "ensayos_cilindro_deslizamiento",
                result.get("ensayo", {}).get("id") if isinstance(result.get("ensayo"), dict) else None,
                warnings,
            )
        return 201, result

    if path == "/api/programa-deslizado/aplicar-receta":
        colado_id = int(payload["colado_id"])
        with connect(db_path) as conn:
            init_db(conn)
            schedule = get_cylinder_test_schedule(conn, colado_id, include_layers=False)
            suggestion = (schedule.get("estado_ensayo") or {}).get("receta_sugerida")
            programa = schedule.get("programa") or {}
            if not suggestion and programa:
                speed = float(programa.get("speed_cm_h") or 0)
                suggestion = {
                    "avance_objetivo_cm": programa.get("step_cm"),
                    "intervalo_objetivo_min": programa.get("step_minutes"),
                    "velocidad_objetivo_cm_h": speed,
                    "tolerancia_velocidad_min_cm_h": max(0.0, speed - 5.0),
                    "tolerancia_velocidad_max_cm_h": speed + 5.0,
                    "motivo": f"Receta aplicada desde programa de cilindro {programa.get('escenario')}.",
                }
            if not suggestion:
                raise ValueError("No hay escenario de cilindro activo para aplicar receta.")
            item_id = upsert_advance_recipe(
                conn,
                {
                    "colado_id": colado_id,
                    "fecha_hora": payload.get("fecha_hora") or datetime.now().isoformat(timespec="seconds"),
                    "avance_objetivo_cm": suggestion.get("avance_objetivo_cm"),
                    "intervalo_objetivo_min": suggestion.get("intervalo_objetivo_min"),
                    "tolerancia_velocidad_min_cm_h": suggestion.get("tolerancia_velocidad_min_cm_h"),
                    "tolerancia_velocidad_max_cm_h": suggestion.get("tolerancia_velocidad_max_cm_h"),
                    "motivo": suggestion.get("motivo") or "Receta aplicada desde ensayo de cilindro.",
                    "operador": payload.get("operador"),
                    "supervisor": payload.get("supervisor"),
                },
            )
            recipe = get_active_advance_recipe(conn, colado_id)
        return 201, {"id": item_id, "receta_activa": recipe, "programa": programa}

    if path == "/api/simular-curva":
        with connect(db_path) as conn:
            init_db(conn)
            colado = get_colado(conn, int(payload["colado_id"]))
            if not colado:
                raise ValueError("Colado no encontrado.")
            curve_id = int(payload.get("curva_id") or colado.get("curva_id") or 0)
            if not curve_id:
                raise ValueError("Selecciona una curva para simular.")
            count = simulate_curve_readings(
                conn,
                int(payload["colado_id"]),
                curve_id,
                float(payload.get("interval_minutes") or 5),
                bool(payload.get("replace_existing")),
            )
        return 201, {"lecturas_importadas": count}

    if path == "/api/simular-operacion":
        with connect(db_path) as conn:
            init_db(conn)
            colado_id = int(payload["colado_id"])
            colado = get_colado(conn, colado_id)
            if not colado:
                raise ValueError("Colado no encontrado.")
            start_time = payload.get("fecha_hora_inicio") or payload.get("start_time") or datetime.now().isoformat(timespec="minutes")
            count = simulate_operational_advances(
                conn,
                colado_id,
                start_time,
                int(payload.get("pasos") or payload.get("steps") or 12),
                bool(payload.get("replace_existing")),
                payload.get("operador") or "Simulador",
            )
            state = calculate_mold_state(conn, colado_id)
        return 201, {"avances_generados": count, "estado_molde": state}

    return None


def handle_put(path: str, db_path: Path, payload: dict[str, Any], path_id) -> tuple[int, dict[str, Any]] | None:
    if path.startswith("/api/colados/"):
        colado_id = path_id(path, "/api/colados/")
        with connect(db_path) as conn:
            init_db(conn)
            updated = update_colado(conn, colado_id, payload)
        return 200, {"colado": updated}
    if path.startswith("/api/descargas/"):
        descarga_id = path_id(path, "/api/descargas/")
        with connect(db_path) as conn:
            init_db(conn)
            existing = conn.execute("SELECT * FROM descargas_olla WHERE id = ?", (descarga_id,)).fetchone()
            if not existing:
                raise ValueError("Descarga/olla no encontrada.")
            _ensure_colado_open_for_operation(conn, int(existing["colado_id"]))
            warnings = require_timing_confirmation(
                payload,
                existing_loads=get_descargas(conn, int(existing["colado_id"])),
                current_load_id=descarga_id,
            )
            updated = update_descarga(conn, descarga_id, payload)
            _audit_critical_correction(
                conn,
                payload | {"colado_id": updated["colado_id"]},
                "CORRECT_TRUCK_LOAD",
                "descargas_olla",
                descarga_id,
                dict(existing),
                updated,
                "Recalculo de madurez de zona por correccion de olla.",
            )
            _audit_confirmed_quality_warnings(
                conn,
                payload | {"colado_id": updated["colado_id"]},
                "UPDATE_DESCARGA_WITH_WARNINGS",
                "descargas_olla",
                descarga_id,
                warnings,
            )
            colado_id = int(updated["colado_id"])
            state = calculate_mold_state(conn, colado_id)
        return 200, {"descarga": updated, "estado_molde": state}
    return None


def handle_delete(path: str, db_path: Path, path_id) -> tuple[int, dict[str, Any]] | None:
    if path.startswith("/api/colados/"):
        colado_id = path_id(path, "/api/colados/")
        backup = create_sqlite_backup(db_path, f"before_delete_colado_{colado_id}")
        with connect(db_path) as conn:
            init_db(conn)
            delete_colado(conn, colado_id)
        return 200, {"deleted": True, "id": colado_id, "backup": backup}
    return None


__all__ = ["handle_delete", "handle_post", "handle_put"]


def _audit_confirmed_quality_warnings(
    conn,
    payload: dict[str, Any],
    action: str,
    entity: str,
    entity_id: Any,
    warnings: list[dict[str, Any]],
) -> None:
    if not warnings:
        return
    insert_audit(
        conn,
        action,
        entity,
        entity_id=int(entity_id) if entity_id not in (None, "") else None,
        colado_id=int(payload["colado_id"]) if payload.get("colado_id") not in (None, "") else None,
        operator=payload.get("operador"),
        reason=payload.get("motivo") or payload.get("observaciones") or "Confirmacion de horarios sospechosos",
        detail={"advertencias": warnings, "impacto": "Recalculo de madurez/programa con datos confirmados."},
    )
    conn.commit()


def _audit_critical_correction(
    conn,
    payload: dict[str, Any],
    action: str,
    entity: str,
    entity_id: Any,
    previous: dict[str, Any],
    current: dict[str, Any],
    impact: str,
) -> None:
    changes = {
        key: {"antes": previous.get(key), "despues": current.get(key)}
        for key in sorted(set(previous) | set(current))
        if previous.get(key) != current.get(key)
        and key in {
            "numero_olla",
            "volumen_m3",
            "hora_salida_planta",
            "hora_llegada_obra",
            "hora_inicio_descarga",
            "hora_fin_descarga",
            "temperatura_llegada_c",
            "temperatura_salida_c",
            "revenimiento_cm",
            "estado_operativo",
            "t_fabricacion",
            "resultado_4h",
            "resultado_5h",
            "resultado_6h",
            "escenario_activo",
            "start_zone",
            "layer_thickness_cm",
            "total_layers",
        }
    }
    if not changes:
        return
    insert_audit(
        conn,
        action,
        entity,
        entity_id=int(entity_id) if entity_id not in (None, "") else None,
        colado_id=int(payload["colado_id"]) if payload.get("colado_id") not in (None, "") else None,
        operator=payload.get("operador"),
        reason=payload.get("motivo") or payload.get("observaciones") or "Correccion critica",
        detail={"cambios": changes, "impacto": impact},
    )
    conn.commit()


_CLOSED_BLOCKED_POST_PATHS = {
    "/api/lecturas",
    "/api/sensor-readings",
    "/api/eventos",
    "/api/descargas",
    "/api/ollas/registrar-zona",
    "/api/colados/inicializar-arranque",
    "/api/zonas",
    "/api/zonas/generar",
    "/api/zonas/asegurar-continuidad",
    "/api/zonas/liberar-por-criterio",
    "/api/lecturas-zona",
    "/api/avances",
    "/api/avances/registrar-5min",
    "/api/scada/confirmar-avance",
    "/api/scada/alarmas/reconocer",
    "/api/turnos",
    "/api/turnos/cerrar",
    "/api/receta-avance",
    "/api/programa-deslizado",
    "/api/programa-deslizado/ensayo",
    "/api/programa-deslizado/aplicar-receta",
    "/api/simular-curva",
    "/api/simular-operacion",
    "/api/modelo/ajustes",
}


def _blocks_closed_colado(path: str) -> bool:
    return path in _CLOSED_BLOCKED_POST_PATHS


def _ensure_colado_open_for_operation(conn, colado_id: int) -> None:
    colado = get_colado(conn, colado_id)
    if not colado:
        raise ValueError("Colado no encontrado.")
    if str(colado.get("estado") or "").upper() == "CERRADO":
        raise ValueError("El colado esta CERRADO. Reabre el colado o edita la fecha de cierre antes de registrar cambios operativos.")
