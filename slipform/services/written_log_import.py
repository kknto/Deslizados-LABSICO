"""Import helpers for handwritten slipform log transcriptions."""

from __future__ import annotations

import base64
import csv
import io
import mimetypes
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from slipform.domain.validation import normalize_datetime
from slipform.mold import calculate_mold_state
from slipform.repositories.audit_repo import insert_audit
from slipform.repositories.avances_repo import get_advances, insert_mold_advance
from slipform.repositories.colados_repo import get_colado
from slipform.repositories.descargas_repo import get_descargas
from slipform.repositories.events_repo import insert_slide_event
from slipform.repositories.evidencia_repo import insert_photo_evidence
from slipform.repositories.scada_repo import insert_field_release
from slipform.repositories.zonas_repo import create_zone, get_zones, register_truck_zone
from slipform.services.backups import create_sqlite_backup

OLLAS_COLUMNS = [
    "numero_olla",
    "hora_salida_planta",
    "hora_llegada_obra",
    "hora_inicio_descarga",
    "hora_fin_descarga",
    "temperatura_llegada_c",
    "revenimiento_cm",
    "zona_numero",
    "altura_capa_cm",
    "hora_4h",
    "hora_5h",
    "hora_6h",
    "fuente_imagen",
    "observaciones",
]

EVENTOS_COLUMNS = [
    "fecha_hora",
    "hora_original",
    "tipo_evento",
    "descripcion_original",
    "decision_tomada",
    "resultado_fisico",
    "supervisor",
    "fuente_imagen",
    "linea_fuente",
]

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
ZONE_HEIGHT_CM = 30.0
ADVANCE_IMPORT_ORIGIN = "importacion_bitacora_deslizamiento"
WRITTEN_LOG_EVENT_PREFIX = "Importado de bitacora escrita."


def ensure_written_log_templates(project_root: Path) -> dict[str, Any]:
    target = Path(project_root) / "Bitacora_escrita" / "transcripcion"
    target.mkdir(parents=True, exist_ok=True)
    ollas_path = target / "ollas_deslizado.csv"
    eventos_path = target / "eventos_deslizado.csv"
    _write_template(ollas_path, OLLAS_COLUMNS)
    _write_template(eventos_path, EVENTOS_COLUMNS)
    return {
        "directorio": str(target),
        "ollas": str(ollas_path),
        "eventos": str(eventos_path),
        "columnas_ollas": OLLAS_COLUMNS,
        "columnas_eventos": EVENTOS_COLUMNS,
    }


def preview_written_log_import(conn, payload: dict[str, Any]) -> dict[str, Any]:
    colado_id = int(payload["colado_id"])
    _ensure_colado(conn, colado_id)
    base_date = _base_date(payload)
    mode = _mode(payload)
    options = _import_options(payload)
    existing_loads = {str(row["numero_olla"]): row for row in get_descargas(conn, colado_id)}
    existing_zones = {int(row["zona_numero"]): row for row in get_zones(conn, colado_id)}
    existing_advances = get_advances(conn, colado_id)
    existing_imported_events = _count_imported_written_log_events(conn, colado_id)
    parsed_ollas = _parse_ollas_csv(payload.get("ollas_csv") or "", base_date, existing_loads, existing_zones, mode)
    parsed_events = _apply_event_import_mode(
        _parse_events_csv(payload.get("eventos_csv") or "", base_date),
        options["modo_eventos_importados"],
        existing_imported_events,
    )
    start_offset = _start_offset_preview(options["primera_zona_fresca"], existing_zones)
    parsed_advances = _parse_event_advances(
        parsed_events,
        existing_advances,
        options,
        inherited_cm=float(start_offset["avance_previo_cm"]),
        operador=payload.get("operador"),
    )
    evidence = _evidence_preview(_project_root_from_payload(payload), payload.get("evidence_folder"))
    summary = _summary(parsed_ollas, parsed_events, evidence, start_offset, parsed_advances)
    insert_audit(
        conn,
        "IMPORT_BITACORA_ESCRITA_PREVIEW",
        "bitacora_escrita",
        colado_id=colado_id,
        operator=payload.get("operador"),
        reason="Vista previa de importacion de bitacora escrita.",
        detail=summary,
    )
    conn.commit()
    return {
        "colado_id": colado_id,
        "fecha_base": base_date.isoformat(),
        "modo_existentes": mode,
        "opciones": options,
        "arranque_historico": start_offset,
        "ollas": parsed_ollas,
        "eventos": parsed_events,
        "avances_deslizamiento": parsed_advances,
        "evidencia": evidence,
        "resumen": summary,
        "puede_importar": summary["errores"] == 0,
    }


def commit_written_log_import(conn, db_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    preview = preview_written_log_import(conn, payload)
    if not preview["puede_importar"]:
        raise ValueError("Corrige los errores de la vista previa antes de importar.")
    backup = create_sqlite_backup(Path(db_path), "pre_import_bitacora_escrita")
    colado_id = int(payload["colado_id"])
    imported_loads = 0
    updated_loads = 0
    skipped_loads = 0
    imported_events = 0
    imported_advances = 0
    imported_evidence = 0
    replaced_events = 0

    start_time = _historical_start_time(preview, payload)
    _align_colado_start_for_historical_import(conn, colado_id, start_time, payload)
    _ensure_historical_previous_zones(conn, colado_id, preview["arranque_historico"], start_time, payload)
    if preview["eventos"].get("reemplazar_importados"):
        replaced_events = _delete_imported_written_log_events(conn, colado_id)

    for item in preview["ollas"]["filas"]:
        if item["estado"] == "omitir":
            skipped_loads += 1
            continue
        item["payload"]["colado_id"] = colado_id
        result = register_truck_zone(conn, item["payload"])
        if result.get("descarga_creada") or result.get("zona_creada"):
            imported_loads += 1
        else:
            updated_loads += 1
        imported_events += _insert_cylinder_time_events(conn, colado_id, item)

    for item in preview["eventos"]["filas"]:
        if item["estado"] != "importar":
            continue
        item["payload"]["colado_id"] = colado_id
        insert_slide_event(conn, item["payload"])
        imported_events += 1

    for item in preview["avances_deslizamiento"]["filas"]:
        if item["estado"] != "importar":
            continue
        item["payload"]["colado_id"] = colado_id
        insert_mold_advance(conn, item["payload"])
        imported_advances += 1

    for image in preview["evidencia"]["imagenes"]:
        if _evidence_exists(conn, colado_id, image["nombre"]):
            continue
        insert_photo_evidence(
            conn,
            {
                "colado_id": colado_id,
                "fecha_hora": payload.get("fecha_hora_evidencia") or f"{preview['fecha_base']}T00:00",
                "descripcion": f"Bitacora escrita importada: {image['nombre']}",
                "operador": payload.get("operador"),
                "imagen_data_url": _image_data_url(Path(image["ruta"])),
            },
        )
        imported_evidence += 1

    state = calculate_mold_state(conn, colado_id) if get_zones(conn, colado_id) else None
    detail = {
        "fecha_base": preview["fecha_base"],
        "modo_existentes": preview["modo_existentes"],
        "ollas_importadas": imported_loads,
        "ollas_actualizadas": updated_loads,
        "ollas_omitidas": skipped_loads,
        "eventos_importados": imported_events,
        "eventos_reemplazados": replaced_events,
        "avances_importados": imported_advances,
        "evidencias_importadas": imported_evidence,
        "backup": backup,
    }
    insert_audit(
        conn,
        "IMPORT_BITACORA_ESCRITA_COMMIT",
        "bitacora_escrita",
        colado_id=colado_id,
        operator=payload.get("operador"),
        reason="Importacion de bitacora escrita confirmada.",
        detail=detail,
    )
    conn.commit()
    return {
        "ok": True,
        "backup": backup,
        "resumen": detail,
        "estado_molde": state,
        "preview": preview,
    }


def project_root_for_db(db_path: Path) -> Path:
    path = Path(db_path)
    return path.parent.parent if path.parent.name.lower() == "data" else path.parent


def _write_template(path: Path, columns: list[str]) -> None:
    if path.exists():
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()


def _base_date(payload: dict[str, Any]) -> date:
    raw = str(payload.get("fecha_base") or "2026-08-04").strip()
    return datetime.fromisoformat(raw[:10]).date()


def _mode(payload: dict[str, Any]) -> str:
    mode = str(payload.get("modo_existentes") or "omitir").strip().lower()
    if mode not in {"omitir", "actualizar"}:
        raise ValueError("Modo de existentes invalido. Usa omitir o actualizar.")
    return mode


def _import_options(payload: dict[str, Any]) -> dict[str, Any]:
    first_fresh = _to_int(payload.get("primera_zona_fresca") or payload.get("primera_zona_nueva") or 1)
    if first_fresh is None or first_fresh < 1:
        raise ValueError("Primera zona fresca debe ser mayor o igual a 1.")
    advance_mode = str(payload.get("modo_avances_existentes") or "bloquear").strip().lower()
    if advance_mode not in {"bloquear"}:
        raise ValueError("Modo de avances existentes invalido. Usa bloquear.")
    event_mode = str(payload.get("modo_eventos_importados") or "bloquear").strip().lower()
    if event_mode not in {"bloquear", "reemplazar_importados"}:
        raise ValueError("Modo de eventos importados invalido. Usa bloquear o reemplazar_importados.")
    interpretation = str(payload.get("interpretacion_avance_deslizado") or "acumulado_desde_inicio").strip().lower()
    if interpretation != "acumulado_desde_inicio":
        raise ValueError("La bitacora Lite solo interpreta el avance como acumulado desde inicio del deslizado.")
    return {
        "primera_zona_fresca": first_fresh,
        "crear_avances_desde_eventos": _bool(payload.get("crear_avances_desde_eventos")),
        "interpretacion_avance_deslizado": interpretation,
        "modo_avances_existentes": advance_mode,
        "modo_eventos_importados": event_mode,
    }


def _project_root_from_payload(payload: dict[str, Any]) -> Path:
    root = payload.get("_project_root")
    return Path(root) if root else Path.cwd()


def _parse_ollas_csv(
    text: str,
    base_date: date,
    existing_loads: dict[str, Any],
    existing_zones: dict[int, Any],
    mode: str,
) -> dict[str, Any]:
    rows = _read_csv_rows(text)
    parsed = []
    previous_total: float | None = None
    day_offset = 0
    for index, row in enumerate(rows, start=2):
        errors: list[str] = []
        warnings: list[str] = []
        number = _to_int(row.get("numero_olla"))
        zone_number = _to_int(row.get("zona_numero")) or number
        if number is None:
            errors.append("numero_olla requerido.")
        if zone_number is None:
            errors.append("zona_numero requerido.")
        salida, previous_total, day_offset, salida_error = _datetime_from_row_time(
            row.get("hora_salida_planta"), base_date, previous_total, day_offset
        )
        if salida_error:
            errors.append(f"hora_salida_planta invalida: {row.get('hora_salida_planta') or ''}.")
        llegada = _optional_datetime_from_time(row.get("hora_llegada_obra"), base_date, salida)
        inicio = _optional_datetime_from_time(row.get("hora_inicio_descarga"), base_date, llegada or salida)
        fin = _optional_datetime_from_time(row.get("hora_fin_descarga"), base_date, inicio or llegada or salida)
        height = _to_float(row.get("altura_capa_cm"))
        if height is not None and abs(height - 30.0) > 0.01:
            warnings.append(f"Altura de capa {height:g} cm; regla Lite esperada: 30 cm.")
        exists = (number is not None and str(number) in existing_loads) or (zone_number is not None and zone_number in existing_zones)
        status = "error" if errors else "omitir" if exists and mode == "omitir" else "actualizar" if exists else "importar"
        if exists and mode == "omitir":
            warnings.append("Olla/zona existente; se omitira por seguridad.")
        payload = {
            "numero_olla": number or "",
            "zona_numero": zone_number or number or "",
            "colado_id": None,
            "volumen_m3": 5.0,
            "hora_salida_planta": salida,
            "hora_llegada_obra": llegada,
            "hora_inicio_descarga": inicio,
            "hora_fin_descarga": fin,
            "temperatura_llegada_c": _to_float(row.get("temperatura_llegada_c")),
            "revenimiento_cm": _to_float(row.get("revenimiento_cm")),
            "altura_zona_cm": height or 30.0,
            "origen_generacion": "importacion_bitacora_escrita",
            "observaciones": _join_text(
                "Importado de bitacora escrita.",
                row.get("observaciones"),
                f"Fuente: {row.get('fuente_imagen') or 'sin imagen capturada'}.",
            ),
        }
        parsed.append(
            {
                "linea": index,
                "estado": status,
                "numero_olla": number,
                "zona_numero": zone_number,
                "fuente_imagen": row.get("fuente_imagen") or "",
                "payload": payload,
                "horarios_cilindro": _cylinder_times(row, base_date, salida),
                "errores": errors,
                "advertencias": warnings,
            }
        )
    _assign_relative_event_minutes(parsed)
    return {"filas": parsed, "total": len(parsed)}


def _parse_events_csv(text: str, base_date: date) -> dict[str, Any]:
    rows = _read_csv_rows(text)
    parsed = []
    previous_total: float | None = None
    day_offset = 0
    for index, row in enumerate(rows, start=2):
        errors: list[str] = []
        warnings: list[str] = []
        description = str(row.get("descripcion_original") or "").strip()
        if not description:
            warnings.append("descripcion_original vacia; se importara usando tipo, hora y fuente para no perder trazabilidad.")
        if _mentions_free_text_quality_data(description):
            warnings.append("El texto menciona temperatura o revenimiento; se conserva como bitacora y debe compararse contra el CSV de ollas.")
        fecha = str(row.get("fecha_hora") or "").strip()
        if fecha:
            try:
                event_time = normalize_datetime(fecha, timespec="minutes")
            except ValueError:
                event_time = f"{base_date.isoformat()}T00:00"
                errors.append(f"fecha_hora invalida: {fecha}.")
        else:
            event_time, previous_total, day_offset, time_error = _datetime_from_row_time(
                row.get("hora_original"), base_date, previous_total, day_offset
            )
            if time_error:
                event_time = f"{base_date.isoformat()}T00:00"
                warnings.append("Hora original ilegible; se importara a 00:00 y debe revisarse.")
        status = "error" if errors else "importar"
        payload = {
            "colado_id": None,
            "fecha_hora": event_time,
            "decision_tomada": row.get("decision_tomada") or row.get("tipo_evento") or "REGISTRO_BITACORA",
            "resultado_fisico": row.get("resultado_fisico") or "registro_escrito",
            "observacion": _join_text(
                WRITTEN_LOG_EVENT_PREFIX,
                description,
                f"Hora original: {row.get('hora_original') or fecha or 'sin hora'}.",
                f"Fuente: {row.get('fuente_imagen') or 'sin imagen capturada'} linea {row.get('linea_fuente') or index}.",
            ),
            "supervisor": row.get("supervisor"),
        }
        parsed.append(
            {
                "linea": index,
                "estado": status,
                "fecha_hora": event_time,
                "tipo_evento": row.get("tipo_evento") or "",
                "fuente_imagen": row.get("fuente_imagen") or "",
                "descripcion": description,
                "payload": payload,
                "errores": errors,
                "advertencias": warnings,
            }
        )
    return {"filas": parsed, "total": len(parsed)}


def _apply_event_import_mode(events: dict[str, Any], mode: str, existing_count: int) -> dict[str, Any]:
    events["modo_eventos_importados"] = mode
    events["existentes_importados"] = existing_count
    events["reemplazar_importados"] = False
    events["errores"] = list(events.get("errores") or [])
    events["advertencias"] = list(events.get("advertencias") or [])
    importable = [row for row in events.get("filas") or [] if row.get("estado") == "importar"]
    if existing_count <= 0 or not importable:
        return events
    if mode == "bloquear":
        events["errores"].append(
            f"Ya existen {existing_count} eventos importados de bitacora escrita. Usa Reemplazar eventos importados para cargar el CSV corregido sin duplicar."
        )
        for row in importable:
            row["estado"] = "bloqueado"
        return events
    events["reemplazar_importados"] = True
    events["advertencias"].append(
        f"Se reemplazaran {existing_count} eventos importados previamente por {len(importable)} eventos del CSV actual."
    )
    return events


def _start_offset_preview(first_fresh_zone: int, existing_zones: dict[int, Any]) -> dict[str, Any]:
    rows = []
    errors: list[str] = []
    warnings: list[str] = []
    for zone_number in range(1, first_fresh_zone):
        existing = existing_zones.get(zone_number)
        inherited = existing and str(existing.get("origen_generacion") or "").lower() == "existente_previo"
        if existing and not inherited:
            duplicate_target = _fresh_zone_sharing_load(existing, existing_zones, first_fresh_zone)
            if duplicate_target:
                message = (
                    f"Zona previa {zone_number} ya existe como zona real, pero comparte la misma olla con Zona "
                    f"{duplicate_target}; se convertira a existente previa al confirmar."
                )
                warnings.append(message)
                status = "corregir"
            else:
                message = f"Zona previa {zone_number} ya existe como zona real; no se puede convertir automaticamente en existente previa."
                errors.append(message)
                status = "error"
        elif inherited:
            status = "existente"
        else:
            status = "crear"
        rows.append(
            {
                "zona_numero": zone_number,
                "zona_colado_id": int(existing["id"]) if existing and existing.get("id") not in (None, "") else None,
                "estado": status,
                "errores": [message] if status == "error" else [],
                "advertencias": [message] if status == "corregir" else [],
            }
        )
    inherited_count = max(0, first_fresh_zone - 1)
    return {
        "primera_zona_fresca": first_fresh_zone,
        "zonas_previas": rows,
        "zonas_previas_total": inherited_count,
        "avance_previo_cm": round(inherited_count * ZONE_HEIGHT_CM, 3),
        "errores": errors,
        "advertencias": warnings,
    }


def _parse_event_advances(
    events: dict[str, Any],
    existing_advances: list[dict[str, Any]],
    options: dict[str, Any],
    inherited_cm: float,
    operador: Any,
) -> dict[str, Any]:
    enabled = bool(options.get("crear_avances_desde_eventos"))
    result = {
        "habilitado": enabled,
        "interpretacion": options.get("interpretacion_avance_deslizado") or "acumulado_desde_inicio",
        "modo_existentes": options.get("modo_avances_existentes") or "bloquear",
        "filas": [],
        "total": 0,
        "importar": 0,
        "avance_final_cm": 0.0,
        "avance_total_visible_cm": round(float(inherited_cm), 3),
        "errores": [],
        "advertencias": [],
    }
    if not enabled:
        return result
    if existing_advances and result["modo_existentes"] == "bloquear":
        result["errores"].append("Ya existen avances del molde en este colado; por seguridad la importacion de avances queda bloqueada.")

    previous_value: float | None = None
    previous_time: datetime | None = None
    first_advance_time: datetime | None = None
    for row in events.get("filas") or []:
        if str(row.get("tipo_evento") or "").strip().lower() != "deslizado":
            continue
        value = _extract_slide_advance_value(row.get("descripcion") or "")
        if value is None:
            continue
        errors = list(row.get("errores") or [])
        warnings = []
        event_time = _safe_dt(row.get("fecha_hora"))
        if event_time is None:
            errors.append("fecha_hora invalida para crear avance.")
        if event_time is not None and first_advance_time is None and not errors:
            first_advance_time = event_time
        elapsed_min = (
            round((event_time - first_advance_time).total_seconds() / 60.0, 3)
            if event_time is not None and first_advance_time is not None
            else None
        )
        if value <= 0:
            errors.append("avance acumulado debe ser mayor a 0 cm.")
        if previous_value is not None and value <= previous_value:
            errors.append(f"avance acumulado {value:g} cm no es mayor que el previo {previous_value:g} cm.")
        delta = value - (previous_value or 0.0)
        if delta > 0 and abs(delta - 3.0) > 0.75:
            warnings.append(f"salto de avance {delta:g} cm; revisar si la fila representa avance acumulado.")
        interval = _extract_interval_minutes(row.get("descripcion") or "")
        if interval is None and previous_time is not None and event_time is not None:
            interval = (event_time - previous_time).total_seconds() / 60.0
        speed = delta / (interval / 60.0) if interval and interval > 0 and delta > 0 else None
        status = "error" if errors else "bloqueado" if result["errores"] else "importar"
        payload = {
            "colado_id": None,
            "fecha_hora": row.get("fecha_hora"),
            "avance_cm": round(delta, 3),
            "avance_acumulado_cm": round(value, 3),
            "minuto_transcurrido": elapsed_min,
            "intervalo_minutos": round(interval, 3) if interval else None,
            "velocidad_real_cm_h": round(speed, 3) if speed else None,
            "origen": ADVANCE_IMPORT_ORIGIN,
            "asegurar_continuidad": False,
            "observacion": _join_text(
                "IMPORT_BITACORA_DESLIZAMIENTO.",
                f"Linea {row.get('linea')}.",
                f"Fuente: {row.get('fuente_imagen') or 'sin imagen'}.",
                f"Descripcion: {row.get('descripcion') or ''}",
            ),
            "operador": operador,
        }
        result["filas"].append(
            {
                "linea": row.get("linea"),
                "estado": status,
                "fecha_hora": row.get("fecha_hora"),
                "avance_acumulado_cm": round(value, 3),
                "avance_cm": round(delta, 3),
                "avance_total_visible_cm": round(inherited_cm + value, 3),
                "fuente_imagen": row.get("fuente_imagen") or "",
                "descripcion": row.get("descripcion") or "",
                "payload": payload,
                "errores": errors,
                "advertencias": warnings,
            }
        )
        if not errors:
            previous_value = value
            previous_time = event_time
    result["total"] = len(result["filas"])
    result["importar"] = sum(1 for row in result["filas"] if row.get("estado") == "importar")
    imported_rows = [row for row in result["filas"] if row.get("estado") in {"importar", "bloqueado"}]
    if imported_rows:
        final = float(imported_rows[-1]["avance_acumulado_cm"])
        result["avance_final_cm"] = round(final, 3)
        result["avance_total_visible_cm"] = round(inherited_cm + final, 3)
    if not result["filas"]:
        result["advertencias"].append("No se detectaron avances acumulados validos en eventos tipo Deslizado.")
    return result


def _fresh_zone_sharing_load(existing_zone: dict[str, Any], existing_zones: dict[int, Any], first_fresh_zone: int) -> int | None:
    load_id = existing_zone.get("descarga_olla_id")
    if load_id in (None, ""):
        return None
    for zone_number, zone in existing_zones.items():
        if int(zone_number) < first_fresh_zone:
            continue
        if zone.get("descarga_olla_id") == load_id:
            return int(zone_number)
    return None


def _historical_start_time(preview: dict[str, Any], payload: dict[str, Any]) -> str:
    explicit = payload.get("hora_inicio_operativo") or payload.get("fecha_hora_arranque")
    if explicit:
        return normalize_datetime(explicit, timespec="minutes")
    candidates: list[str] = []
    for group_name in ("eventos", "ollas"):
        for row in preview.get(group_name, {}).get("filas") or []:
            value = row.get("fecha_hora") or (row.get("payload") or {}).get("hora_salida_planta")
            if value:
                candidates.append(str(value))
    if candidates:
        return min(candidates)
    return f"{preview['fecha_base']}T00:00"


def _ensure_historical_previous_zones(
    conn,
    colado_id: int,
    start_offset: dict[str, Any],
    start_time: str,
    payload: dict[str, Any],
) -> int:
    created = 0
    for item in start_offset.get("zonas_previas") or []:
        if item.get("estado") == "error":
            raise ValueError("No se pueden crear zonas previas porque hay conflictos con zonas existentes.")
        if item.get("estado") == "existente":
            continue
        if item.get("estado") == "corregir" and item.get("zona_colado_id"):
            zone_id = int(item["zona_colado_id"])
            conn.execute(
                """
                UPDATE zonas_colado
                SET descarga_olla_id = NULL,
                    volumen_m3 = 0,
                    hora_salida_planta = NULL,
                    hora_inicio_llenado = ?,
                    hora_fin_llenado = NULL,
                    hora_referencia_madurez = ?,
                    temperatura_inicial_c = COALESCE(temperatura_inicial_c, ?),
                    origen_generacion = 'existente_previo',
                    estado = 'EXISTENTE_PREVIO'
                WHERE id = ?
                """,
                (start_time, start_time, payload.get("temperatura_concreto_c") or 23, zone_id),
            )
        else:
            zone_id = create_zone(
                conn,
                {
                    "colado_id": colado_id,
                    "zona_numero": item["zona_numero"],
                    "elevacion_inferior_cm": (int(item["zona_numero"]) - 1) * ZONE_HEIGHT_CM,
                    "elevacion_superior_cm": int(item["zona_numero"]) * ZONE_HEIGHT_CM,
                    "volumen_m3": 0,
                    "hora_salida_planta": start_time,
                    "hora_inicio_llenado": start_time,
                    "hora_referencia_madurez": start_time,
                    "temperatura_inicial_c": payload.get("temperatura_concreto_c") or 23,
                    "origen_generacion": "existente_previo",
                    "estado": "EXISTENTE_PREVIO",
                },
            )
            conn.execute("UPDATE zonas_colado SET hora_salida_planta = NULL WHERE id = ?", (zone_id,))
        insert_field_release(
            conn,
            {
                "colado_id": colado_id,
                "zona_colado_id": zone_id,
                "fecha_hora": start_time,
                "madurez_calculada_pct": 0.0,
                "madurez_operativa_pct": 90.0,
                "temperatura_concreto_c": payload.get("temperatura_concreto_c") or 23,
                "condicion_observada": "existente_previo",
                "checklist": {
                    "no_desmorona": True,
                    "no_se_pega": True,
                    "acabado_aceptable": True,
                    "sin_arrastre": True,
                },
                "motivo": "Importacion de bitacora escrita: zona previa existente.",
                "operador": payload.get("operador"),
                "supervisor": payload.get("supervisor") or "Importacion",
            },
        )
        item["zona_colado_id"] = zone_id
        created += 1
    if created:
        insert_audit(
            conn,
            "IMPORT_BITACORA_ESCRITA_ZONAS_PREVIAS",
            "bitacora_escrita",
            colado_id=colado_id,
            operator=payload.get("operador"),
            reason="Creacion de zonas previas existentes desde bitacora escrita.",
            detail={
                "primera_zona_fresca": start_offset.get("primera_zona_fresca"),
                "zonas_previas_creadas": created,
                "avance_previo_cm": start_offset.get("avance_previo_cm"),
            },
        )
    return created


def _align_colado_start_for_historical_import(conn, colado_id: int, start_time: str, payload: dict[str, Any]) -> None:
    colado = _ensure_colado(conn, colado_id)
    current = colado.get("fecha_hora_inicio") or colado.get("hora_colocacion_en_molde")
    if current:
        current_dt = _safe_dt(current)
        start_dt = _safe_dt(start_time)
        if current_dt is not None and start_dt is not None and current_dt <= start_dt:
            return
    conn.execute(
        """
        UPDATE colados
        SET fecha_hora_inicio = ?
        WHERE id = ?
        """,
        (start_time, colado_id),
    )
    insert_audit(
        conn,
        "IMPORT_BITACORA_ESCRITA_AJUSTA_INICIO",
        "colados",
        entity_id=colado_id,
        colado_id=colado_id,
        operator=payload.get("operador"),
        reason="Alineacion del inicio operativo con la bitacora historica importada.",
        detail={"inicio_anterior": current, "inicio_historico": start_time},
    )


def _read_csv_rows(text: str) -> list[dict[str, str]]:
    clean = str(text or "").lstrip("\ufeff").strip()
    if not clean:
        return []
    sample = clean[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(clean), dialect=dialect)
    return [{str(k or "").strip(): str(v or "").strip() for k, v in row.items()} for row in reader]


def _assign_relative_event_minutes(rows: list[dict[str, Any]]) -> None:
    times = [_safe_dt(row.get("fecha_hora")) for row in rows if row.get("estado") != "error"]
    first = min((item for item in times if item is not None), default=None)
    if first is None:
        return
    for row in rows:
        event_time = _safe_dt(row.get("fecha_hora"))
        if event_time is None:
            continue
        row["payload"]["minuto_transcurrido"] = round((event_time - first).total_seconds() / 60.0, 3)


def _datetime_from_row_time(
    raw: Any,
    base_date: date,
    previous_total: float | None,
    day_offset: int,
) -> tuple[str | None, float | None, int, bool]:
    minute = _time_to_minute(raw)
    if minute is None:
        return None, previous_total, day_offset, True
    total = minute + day_offset * 1440
    if previous_total is not None and total < previous_total - 360:
        day_offset += 1
        total = minute + day_offset * 1440
    dt = datetime.combine(base_date, datetime.min.time()) + timedelta(minutes=total)
    return dt.isoformat(timespec="minutes"), total, day_offset, False


def _optional_datetime_from_time(raw: Any, base_date: date, anchor_iso: str | None) -> str | None:
    minute = _time_to_minute(raw)
    if minute is None:
        return None
    anchor = datetime.fromisoformat(anchor_iso) if anchor_iso else datetime.combine(base_date, datetime.min.time())
    candidate = datetime.combine(anchor.date(), datetime.min.time()) + timedelta(minutes=minute)
    if candidate < anchor - timedelta(hours=6):
        candidate += timedelta(days=1)
    return candidate.isoformat(timespec="minutes")


def _time_to_minute(raw: Any) -> int | None:
    text = str(raw or "").strip().lower().replace("hrs", "").replace("hr", "").replace("h", "")
    text = text.replace(";", ":").replace(".", ":").replace(",", ":").strip()
    if not text:
        return None
    parts = [part for part in text.split(":") if part != ""]
    if len(parts) < 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour * 60 + minute


def _cylinder_times(row: dict[str, str], base_date: date, salida: str | None) -> dict[str, str | None]:
    return {
        "4h": _optional_datetime_from_time(row.get("hora_4h"), base_date, salida),
        "5h": _optional_datetime_from_time(row.get("hora_5h"), base_date, salida),
        "6h": _optional_datetime_from_time(row.get("hora_6h"), base_date, salida),
    }


def _insert_cylinder_time_events(conn, colado_id: int, item: dict[str, Any]) -> int:
    count = 0
    for label, when in (item.get("horarios_cilindro") or {}).items():
        if not when:
            continue
        insert_slide_event(
            conn,
            {
                "colado_id": colado_id,
                "fecha_hora": when,
                "decision_tomada": "PROGRAMA_CILINDRO",
                "resultado_fisico": "programado",
                "observacion": f"Horario {label} importado de bitacora escrita para Olla {item.get('numero_olla')} / Zona {item.get('zona_numero')}. Fuente: {item.get('fuente_imagen') or 'sin imagen'}.",
            },
        )
        count += 1
    return count


def _evidence_preview(project_root: Path, evidence_folder: Any) -> dict[str, Any]:
    folder = Path(evidence_folder) if evidence_folder else Path(project_root) / "Bitacora_escrita"
    images = []
    if folder.exists():
        for path in sorted(folder.rglob("*")):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                images.append({"nombre": path.name, "ruta": str(path), "bytes": path.stat().st_size})
    return {"directorio": str(folder), "imagenes": images, "total": len(images)}


def _image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _evidence_exists(conn, colado_id: int, image_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM fotografias_evidencia
        WHERE colado_id = ? AND descripcion LIKE ?
        LIMIT 1
        """,
        (colado_id, f"%{image_name}%"),
    ).fetchone()
    return bool(row)


def _summary(
    ollas: dict[str, Any],
    events: dict[str, Any],
    evidence: dict[str, Any],
    start_offset: dict[str, Any],
    advances: dict[str, Any],
) -> dict[str, int | float]:
    rows = [*(ollas.get("filas") or []), *(events.get("filas") or [])]
    rows.extend(advances.get("filas") or [])
    return {
        "ollas_total": int(ollas.get("total") or 0),
        "ollas_importar": sum(1 for row in ollas.get("filas") or [] if row.get("estado") in {"importar", "actualizar"}),
        "ollas_omitidas": sum(1 for row in ollas.get("filas") or [] if row.get("estado") == "omitir"),
        "eventos_total": int(events.get("total") or 0),
        "eventos_importar": sum(1 for row in events.get("filas") or [] if row.get("estado") == "importar"),
        "eventos_bloqueados": sum(1 for row in events.get("filas") or [] if row.get("estado") == "bloqueado"),
        "eventos_importados_existentes": int(events.get("existentes_importados") or 0),
        "eventos_reemplazar": int(events.get("existentes_importados") or 0) if events.get("reemplazar_importados") else 0,
        "zonas_previas": int(start_offset.get("zonas_previas_total") or 0),
        "avance_previo_cm": float(start_offset.get("avance_previo_cm") or 0.0),
        "avances_detectados": int(advances.get("total") or 0),
        "avances_importar": int(advances.get("importar") or 0),
        "avance_deslizamiento_total": float(advances.get("avance_final_cm") or 0.0),
        "avance_total_visible_estimado": float(advances.get("avance_total_visible_cm") or start_offset.get("avance_previo_cm") or 0.0),
        "imagenes_evidencia": int(evidence.get("total") or 0),
        "errores": (
            sum(len(row.get("errores") or []) for row in rows)
            + len(events.get("errores") or [])
            + len(start_offset.get("errores") or [])
            + len(advances.get("errores") or [])
        ),
        "advertencias": (
            sum(len(row.get("advertencias") or []) for row in rows)
            + len(events.get("advertencias") or [])
            + len(start_offset.get("advertencias") or [])
            + len(advances.get("advertencias") or [])
        ),
    }


def _ensure_colado(conn, colado_id: int) -> dict[str, Any]:
    colado = get_colado(conn, colado_id)
    if not colado:
        raise ValueError("Colado no encontrado.")
    return colado


def _count_imported_written_log_events(conn, colado_id: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM eventos_deslizamiento
        WHERE colado_id = ?
          AND observacion LIKE ?
        """,
        (colado_id, f"{WRITTEN_LOG_EVENT_PREFIX}%"),
    ).fetchone()
    return int(row["total"] if row else 0)


def _delete_imported_written_log_events(conn, colado_id: int) -> int:
    count = _count_imported_written_log_events(conn, colado_id)
    if count <= 0:
        return 0
    conn.execute(
        """
        DELETE FROM eventos_deslizamiento
        WHERE colado_id = ?
          AND observacion LIKE ?
        """,
        (colado_id, f"{WRITTEN_LOG_EVENT_PREFIX}%"),
    )
    insert_audit(
        conn,
        "REPLACE_BITACORA_ESCRITA_EVENTS",
        "eventos_deslizamiento",
        colado_id=colado_id,
        reason="Reemplazo de eventos importados desde CSV corregido.",
        detail={"eventos_eliminados": count},
    )
    conn.commit()
    return count


def _to_float(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text.replace(",", ".")))
    except ValueError:
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "on", "yes", "si", "sí"}
    return bool(value)


def _mentions_free_text_quality_data(text: str) -> bool:
    return bool(re.search(r"\b(rev\.?|revenimiento|temp\.?|temperatura)\b", str(text or ""), re.I))


def _extract_slide_advance_value(text: Any) -> float | None:
    description = str(text or "").strip()
    patterns = [
        r"^\s*(\d+(?:[\.,]\d+)?)\s*(?:cm)?\b",
        r"\bavance(?:\s+acumulado)?\s*(?:de|=|:)?\s*(\d+(?:[\.,]\d+)?)\s*(?:cm)?\b",
        r"\balcanz[oó]\s*(?:a|hasta)?\s*(\d+(?:[\.,]\d+)?)\s*(?:cm)?\b",
        r"\bllega\s*(?:a|hasta)?\s*(\d+(?:[\.,]\d+)?)\s*(?:cm)?\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, description, re.I)
        if match:
            return _to_float(match.group(1))
    return None


def _extract_interval_minutes(text: Any) -> float | None:
    match = re.search(r"\bcada\s+(\d+(?:[\.,]\d+)?)\s*(?:min|m)\b", str(text or ""), re.I)
    return _to_float(match.group(1)) if match else None


def _safe_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _join_text(*parts: Any) -> str:
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


__all__ = [
    "EVENTOS_COLUMNS",
    "OLLAS_COLUMNS",
    "commit_written_log_import",
    "ensure_written_log_templates",
    "preview_written_log_import",
    "project_root_for_db",
]
