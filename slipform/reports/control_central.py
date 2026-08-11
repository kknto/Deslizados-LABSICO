"""Data assembly for the Control Central De Deslizado report."""

from __future__ import annotations

from typing import Any

from slipform.domain.validation import parse_datetime
from slipform.db import (
    get_active_project,
    get_advances,
    get_colado,
    get_events,
    get_readings,
    get_zones,
    list_operator_decisions,
    list_operational_alarms,
    list_field_releases,
    list_audit,
    list_photo_evidence,
    list_plumb_readings,
    list_shift_details,
)
from slipform.mold import calculate_mold_state

REPORT_PROGRAMMED_SPEED_CM_H = 14.05
REPORT_PROGRAMMED_INTERVAL_LABEL = "30 cm / 100 min"


def build_control_report_context(conn, colado_id: int) -> dict[str, Any]:
    colado = get_colado(conn, colado_id)
    if not colado:
        return {"colado": None}
    readings = get_readings(conn, colado_id)
    events = get_events(conn, colado_id)
    zones = get_zones(conn, colado_id)
    advances = get_advances(conn, colado_id)
    alarms = list_operational_alarms(conn, colado_id, include_closed=True)
    decisions = list_operator_decisions(conn, colado_id)
    field_releases = list_field_releases(conn, colado_id)
    turnos = list_shift_details(conn, colado_id)
    fotos = list_photo_evidence(conn, colado_id)
    desplomes = list_plumb_readings(conn, colado_id)
    audit = [row for row in list_audit(conn, limit=500) if int(row.get("colado_id") or 0) == int(colado_id)]
    mold_state = calculate_mold_state(conn, colado_id) if zones else None
    project = get_active_project(conn)
    latest_advance = advances[-1] if advances else {}
    start = _operational_start(colado, zones, advances, events)
    end = (advances[-1] or {}).get("fecha_hora") if advances else None
    duration_days = days_between(start, end)
    advance_previous_cm = float((mold_state or {}).get("progreso_operativo", {}).get("avance_previo_cm") or 0.0)
    advance_visible_cm = float((mold_state or {}).get("progreso_operativo", {}).get("avance_total_cm") or latest_advance.get("avance_acumulado_cm") or 0.0)
    total_height_m = float(latest_advance.get("avance_acumulado_cm") or 0) / 100.0
    operational_target_speed = float((mold_state or {}).get("receta_avance", {}).get("velocidad_objetivo_cm_h") or 30)
    summary = {
        "altura_total_deslizada_m": round(total_height_m, 3),
        "altura_visible_m": round(advance_visible_cm / 100.0, 3),
        "altura_previa_m": round(advance_previous_cm / 100.0, 3),
        "ritmo_real_cm_h": latest_advance.get("velocidad_real_cm_h"),
        "ritmo_programado_cm_h": REPORT_PROGRAMMED_SPEED_CM_H,
        "ritmo_programado_detalle": REPORT_PROGRAMMED_INTERVAL_LABEL,
        "ritmo_operativo_receta_cm_h": operational_target_speed,
        "duracion_real_dias": duration_days,
        "periodo_inicio": start,
        "periodo_fin": end,
        "estado_colado": colado.get("estado"),
        "fecha_cierre": colado.get("fecha_cierre"),
        "alarmas": len(alarms),
        "decisiones": len(decisions),
        "desplomes_fuera_tolerancia": len([d for d in desplomes if d.get("estado") != "OK"]),
    }
    if not turnos and advances:
        turnos = build_shift_summary_from_advances(advances)
    operational_log = build_operational_log(readings, advances, decisions, events, alarms, field_releases, audit)
    return {
        "proyecto": project,
        "colado": colado,
        "readings": readings,
        "events": events,
        "zones": zones,
        "advances": advances,
        "alarms": alarms,
        "decisions": decisions,
        "field_releases": field_releases,
        "operational_log": operational_log,
        "bitacora_reporte": build_report_event_log(events),
        "turnos": turnos,
        "fotografias": fotos,
        "desplomes": desplomes,
        "auditoria": audit,
        "mold_state": mold_state,
        "resumen": summary,
    }


def days_between(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        a = parse_datetime(str(start))
        b = parse_datetime(str(end))
    except ValueError:
        return None
    return round(max(0.0, (b - a).total_seconds() / 86400.0), 2)


def build_shift_summary_from_advances(advances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not advances:
        return []
    sorted_advances = sorted(advances, key=lambda item: str(item.get("fecha_hora") or ""))
    groups: dict[str, list[dict[str, Any]]] = {}
    for advance in sorted_advances:
        key = str(advance.get("fecha_hora") or "")[:10] or "sin_fecha"
        groups.setdefault(key, []).append(advance)
    rows: list[dict[str, Any]] = []
    previous_accum = 0.0
    for key in sorted(groups):
        items = groups[key]
        first = items[0]
        last = items[-1]
        start_dt = _safe_parse(first.get("fecha_hora"))
        end_dt = _safe_parse(last.get("fecha_hora"))
        last_accum = float(last.get("avance_acumulado_cm") or previous_accum)
        partial_cm = max(0.0, last_accum - previous_accum)
        elapsed_h = (end_dt - start_dt).total_seconds() / 3600.0 if start_dt and end_dt and end_dt > start_dt else None
        speed = partial_cm / elapsed_h if elapsed_h and elapsed_h > 0 else last.get("velocidad_real_cm_h")
        rows.append(
            {
                "turno": f"Historico {key}",
                "inicio_turno": first.get("fecha_hora"),
                "fin_turno": last.get("fecha_hora"),
                "operador": last.get("operador") or "Importacion",
                "avance_parcial_m": round(partial_cm / 100.0, 3),
                "avance_acumulado_m": round(last_accum / 100.0, 3),
                "ritmo_cm_h": round(float(speed), 3) if speed not in (None, "") else None,
                "observaciones": f"Resumen automatico desde {len(items)} avances importados.",
            }
        )
        previous_accum = last_accum
    return rows


def _operational_start(
    colado: dict[str, Any],
    zones: list[dict[str, Any]],
    advances: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> str | None:
    candidates: list[str] = []
    for zone in zones:
        value = zone.get("hora_salida_planta") or zone.get("hora_inicio_llenado") or zone.get("hora_referencia_madurez")
        if value:
            candidates.append(str(value))
    for advance in advances:
        if advance.get("fecha_hora"):
            candidates.append(str(advance["fecha_hora"]))
    for event in events:
        if event.get("fecha_hora"):
            candidates.append(str(event["fecha_hora"]))
    if candidates:
        return min(candidates)
    return colado.get("fecha_hora_inicio") or colado.get("hora_colocacion_en_molde")


def _safe_parse(value: Any):
    if not value:
        return None
    try:
        return parse_datetime(str(value))
    except ValueError:
        return None


def build_operational_log(
    readings: list[dict[str, Any]],
    advances: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    events: list[dict[str, Any]],
    alarms: list[dict[str, Any]],
    field_releases: list[dict[str, Any]] | None = None,
    audit: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for row in readings:
        entries.append(
            {
                "fecha_hora": row.get("fecha_hora"),
                "tipo": "LECTURA",
                "zona": row.get("zona_numero") or "",
                "detalle": f"Temp concreto {row.get('temperatura_concreto_c')} C; ambiente {row.get('temperatura_ambiente_c')}; HR {row.get('humedad_relativa_pct')}",
                "operador": row.get("origen"),
                "supervisor": "",
                "origen_id": row.get("id"),
            }
        )
    for row in advances:
        entries.append(
            {
                "fecha_hora": row.get("fecha_hora"),
                "tipo": "AVANCE",
                "zona": "",
                "detalle": f"Avance {row.get('avance_cm')} cm; acumulado {row.get('avance_acumulado_cm')} cm; velocidad {row.get('velocidad_real_cm_h')} cm/h",
                "operador": row.get("operador"),
                "supervisor": "",
                "origen_id": row.get("id"),
            }
        )
    for row in decisions:
        entries.append(
            {
                "fecha_hora": row.get("fecha_hora"),
                "tipo": "DECISION",
                "zona": row.get("zona_colado_id") or "",
                "detalle": f"{row.get('recomendacion_sistema')} -> {row.get('decision_operador')}; {row.get('observacion') or ''}",
                "operador": row.get("operador"),
                "supervisor": row.get("supervisor"),
                "origen_id": row.get("id"),
            }
        )
    for row in field_releases or []:
        entries.append(
            {
                "fecha_hora": row.get("fecha_hora"),
                "tipo": "CRITERIO_CAMPO",
                "zona": row.get("zona_numero") or row.get("zona_colado_id") or "",
                "detalle": f"Madurez calculada {row.get('madurez_calculada_pct')}%; operativa {row.get('madurez_operativa_pct')}%; {row.get('motivo') or ''}",
                "operador": row.get("operador"),
                "supervisor": row.get("supervisor"),
                "origen_id": row.get("id"),
            }
        )
    for row in events:
        if _is_sliding_event(row):
            continue
        entries.append(
            {
                "fecha_hora": row.get("fecha_hora"),
                "tipo": _event_type_label(row),
                "zona": "",
                "detalle": _event_detail(row),
                "operador": "",
                "supervisor": row.get("supervisor"),
                "origen_id": row.get("id"),
            }
        )
    for row in alarms:
        entries.append(
            {
                "fecha_hora": row.get("fecha_hora_inicio"),
                "tipo": "ALARMA",
                "zona": row.get("zona_colado_id") or "",
                "detalle": f"{row.get('severidad')} {row.get('tipo')}: {row.get('mensaje')}",
                "operador": row.get("operador_reconoce"),
                "supervisor": "",
                "origen_id": row.get("id"),
            }
        )
    for row in audit or []:
        entries.append(
            {
                "fecha_hora": row.get("fecha_hora"),
                "tipo": "AUDITORIA",
                "zona": "",
                "detalle": f"{row.get('accion')}: {row.get('motivo') or ''}",
                "operador": row.get("operador"),
                "supervisor": "",
                "origen_id": row.get("id"),
            }
        )
    return sorted(entries, key=lambda item: str(item.get("fecha_hora") or ""))


def build_report_event_log(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for row in events:
        if _is_sliding_event(row):
            continue
        entries.append(
            {
                "fecha_hora": row.get("fecha_hora"),
                "tipo": _event_type_label(row),
                "zona": "",
                "detalle": _event_detail(row),
                "operador": "",
                "supervisor": row.get("supervisor"),
                "origen_id": row.get("id"),
            }
        )
    return sorted(entries, key=lambda item: str(item.get("fecha_hora") or ""))


def _is_sliding_event(row: dict[str, Any]) -> bool:
    decision = _normalized_text(row.get("decision_tomada"))
    observation = _normalized_text(row.get("observacion"))
    return decision in {"DESLIZADO", "DESLIZAR"} or observation.startswith("DESLIZADO")


def _event_type_label(row: dict[str, Any]) -> str:
    decision = str(row.get("decision_tomada") or "").strip()
    if not decision:
        return "EVENTO"
    label = decision.replace("_", " ").strip()
    if label.upper() in {"REGISTRO BITACORA", "REGISTRO_BITACORA"}:
        return "BITACORA"
    return label.upper()


def _event_detail(row: dict[str, Any]) -> str:
    observation = _clean_historical_observation(row.get("observacion"))
    result = str(row.get("resultado_fisico") or "").strip()
    if _normalized_text(result) in {"", "REGISTRO ESCRITO", "REGISTRO_ESCRITO"}:
        result = ""
    parts = [part for part in [result, observation] if part]
    return "; ".join(parts) or "Registro de bitacora."


def _clean_historical_observation(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    prefix = "Importado de bitacora escrita."
    if text.startswith(prefix):
        text = text[len(prefix) :].strip()
    for marker in ("Hora original:", "Fuente:"):
        index = text.lower().find(marker.lower())
        if index >= 0:
            text = text[:index].strip()
    return text.strip(" ;.")


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().replace("_", " ").upper()


__all__ = [
    "build_control_report_context",
    "build_operational_log",
    "build_report_event_log",
    "build_shift_summary_from_advances",
    "days_between",
]
