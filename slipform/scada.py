from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .config import DEFAULT_PARAMS
from .core import arrhenius_factor, calculate_maturity, validate_readings
from .domain.validation import normalize_datetime, parse_datetime
from .db import (
    acknowledge_operational_alarm,
    close_stale_operational_alarms,
    get_advances,
    get_events,
    get_readings,
    get_reference_points,
    get_zone,
    get_zone_readings,
    get_zones,
    insert_field_release,
    insert_mold_advance,
    insert_operator_decision,
    latest_active_field_release,
    latest_field_prediction_adjustment,
    list_field_releases,
    list_field_prediction_adjustments,
    list_operator_decisions,
    list_operational_alarms,
    upsert_field_prediction_adjustment,
    upsert_operational_alarm,
)
from .mold import calculate_mold_state


def get_scada_state(conn, colado_id: int, as_of_iso: str | None = None) -> dict[str, Any]:
    mold_state = calculate_mold_state(conn, colado_id, as_of_iso=as_of_iso)
    sync_operational_alarms(conn, mold_state)
    alarms = list_operational_alarms(conn, colado_id)
    next_zone = mold_state.get("zona_en_liberacion") or {}
    status = mold_state.get("estado_operativo") or "SIN_DATOS"
    return {
        "estado_molde": mold_state,
        "estado_scada": _scada_label(status),
        "colado": mold_state.get("colado"),
        "zona_proxima": next_zone,
        "alarmas_activas": alarms,
        "decisiones_recientes": list_operator_decisions(conn, colado_id)[:8],
        "metricas": {
            "madurez_zona_pct": round(float(next_zone.get("avance_madurez") or 0) * 100, 1),
            "edad_zona_h": round(float(next_zone.get("edad_real_h") or 0), 2),
            "temperatura_concreto_c": next_zone.get("temperatura_actual_c"),
            "avance_acumulado_cm": mold_state.get("avance_acumulado_cm"),
            "velocidad_real_cm_h": mold_state.get("velocidad_real_cm_h"),
            "ventana_molde": mold_state.get("ventana_molde"),
            "fuente_temperatura": next_zone.get("fuente_temperatura") or "sin_datos",
            "prediccion_deslizamiento": mold_state.get("prediccion_deslizamiento"),
        },
    }


def sync_operational_alarms(conn, mold_state: dict[str, Any]) -> list[dict[str, Any]]:
    colado_id = int(mold_state["colado"]["id"])
    now = mold_state.get("hora_evaluacion") or datetime.now().isoformat(timespec="seconds")
    active: list[dict[str, Any]] = []
    next_zone = mold_state.get("zona_en_liberacion") or {}
    next_zone_id = int(next_zone["id"]) if next_zone.get("id") else None
    state = mold_state.get("estado_operativo")

    if state == "NO_LIBERAR":
        active.append(
            _alarm(
                colado_id,
                next_zone_id,
                "ZONA_MENOR_90",
                "CRITICA",
                "La zona proxima tiene madurez menor a 90%; no liberar sin espera o supervisor.",
                now,
            )
        )
    if next_zone.get("madurez_override_activa") and float(next_zone.get("avance_madurez_calculada") or 0) < DEFAULT_PARAMS["slide_threshold"]:
        active.append(
            _alarm(
                colado_id,
                next_zone_id,
                "LIBERACION_CRITERIO_CAMPO",
                "MEDIA",
                "Zona marcada lista por inspeccion con madurez calculada menor a 90%.",
                now,
            )
        )
    if state == "RIESGO_AGARROTAMIENTO":
        active.append(
            _alarm(
                colado_id,
                next_zone_id,
                "ZONA_MAYOR_105",
                "ALTA",
                "La zona proxima supera 105% de madurez; vigilar pegado, arrastre o agarrotamiento.",
                now,
            )
        )
    if state == "FALTA_ZONA_SUPERIOR":
        active.append(
            _alarm(
                colado_id,
                None,
                "FALTA_ZONA_SUPERIOR",
                "ALTA",
                "Falta crear zona superior para cubrir la ventana actual del molde.",
                now,
            )
        )
    if state == "MOLDE_INCOMPLETO":
        missing = int(mold_state.get("zonas_requeridas_iniciales") or 4) - int(mold_state.get("zonas_confirmadas_iniciales") or 0)
        active.append(
            _alarm(
                colado_id,
                None,
                "MOLDE_INCOMPLETO",
                "ALTA",
                f"Molde incompleto: faltan {max(0, missing)} olla(s) para completar los primeros 120 cm.",
                now,
            )
        )

    for zone in mold_state.get("zonas_en_molde") or []:
        if not zone.get("hora_referencia_madurez"):
            continue
        if _parse_dt(str(zone["hora_referencia_madurez"])) > _parse_dt(str(now)):
            active.append(
                _alarm(
                    colado_id,
                    int(zone["id"]),
                    "ZONA_HORA_FUTURA",
                    "ALTA",
                    f"Zona {zone['zona_numero']} tiene hora de madurez futura; revisar hora local de captura/evaluacion.",
                    now,
                )
            )

    recipe = mold_state.get("receta_avance") or {}
    target_speed = float(recipe.get("velocidad_objetivo_cm_h") or 30)
    min_speed = float(recipe.get("tolerancia_velocidad_min_cm_h") or max(0, target_speed - 5))
    max_speed = float(recipe.get("tolerancia_velocidad_max_cm_h") or target_speed + 5)
    speed = float(mold_state.get("velocidad_real_cm_h") or 0)
    if speed and not (min_speed <= speed <= max_speed):
        active.append(
            _alarm(
                colado_id,
                None,
                "VELOCIDAD_FUERA_OBJETIVO",
                "MEDIA",
                f"Velocidad real {speed:.1f} cm/h fuera de tolerancia {min_speed:.1f}-{max_speed:.1f} cm/h.",
                now,
            )
        )

    readings = get_readings(conn, colado_id)
    invalid = validate_readings(readings, DEFAULT_PARAMS, now_iso=now)
    for reason in invalid:
        tipo = "SENSOR_VENCIDO" if "vencida" in reason.lower() else "TEMPERATURA_FUERA_RANGO"
        active.append(_alarm(colado_id, None, tipo, "ALTA", reason, now))

    active_keys = {(alarm["zona_colado_id"], alarm["tipo"]) for alarm in active}
    for alarm in active:
        upsert_operational_alarm(conn, alarm)
    close_stale_operational_alarms(conn, colado_id, active_keys, fecha_hora=now)
    return list_operational_alarms(conn, colado_id)


def confirm_scada_advance(conn, payload: dict[str, Any]) -> dict[str, Any]:
    colado_id = int(payload["colado_id"])
    fecha_hora = normalize_datetime(payload.get("fecha_hora") or datetime.now().isoformat(timespec="seconds"))
    scada = get_scada_state(conn, colado_id, as_of_iso=fecha_hora)
    mold_state = scada["estado_molde"]
    status = mold_state.get("estado_operativo") or "SIN_DATOS"
    decision = payload.get("decision_operador") or payload.get("decision") or "AVANZAR"
    wants_advance = decision in {"AVANZAR", "DESLIZAR", "CONTINUAR"}
    wants_early_authorized_advance = (
        status == "NO_LIBERAR"
        and decision == "AVANZAR_BAJO_AUTORIZACION"
        and bool(payload.get("autorizar_avance_inmaduro"))
    )
    if wants_early_authorized_advance:
        wants_advance = True
    if status == "MOLDE_INCOMPLETO" and wants_advance:
        raise ValueError("No se puede deslizar: el molde inicial de 1.20 m todavia esta incompleto.")
    if status in {"FALTA_ZONA_SUPERIOR", "SIN_ZONA_A_LIBERAR", "SIN_ZONAS"} and wants_advance:
        raise ValueError("No se puede deslizar: falta informacion fisica del molde o zona superior.")
    if status == "NO_LIBERAR" and wants_advance and not wants_early_authorized_advance:
        raise ValueError("Para avanzar con madurez insuficiente usa AVANZAR_BAJO_AUTORIZACION.")
    requires_supervisor = status in {"NO_LIBERAR", "CRITICO", "FALTA_ZONA_SUPERIOR", "MOLDE_INCOMPLETO"} and wants_advance
    if requires_supervisor and not payload.get("supervisor"):
        raise ValueError("Avanzar contra una recomendacion critica requiere supervisor.")
    if wants_early_authorized_advance and not str(payload.get("observacion") or "").strip():
        raise ValueError("El avance bajo autorizacion requiere motivo u observacion.")
    if wants_early_authorized_advance and not _checklist_complete(payload.get("checklist") or {}):
        raise ValueError("El avance bajo autorizacion requiere checklist fisico completo.")

    observation = payload.get("observacion")
    if wants_early_authorized_advance:
        observation = f"AVANCE BAJO AUTORIZACION POR MADUREZ INSUFICIENTE. {observation or ''}".strip()

    advance_id: int | None = None
    if wants_advance and payload.get("registrar_avance", True):
        advance_id = insert_mold_advance(
            conn,
            {
                "colado_id": colado_id,
                "fecha_hora": fecha_hora,
                "avance_cm": payload.get("avance_cm") or mold_state["siguiente_avance_5min"]["avance_cm"],
                "intervalo_minutos": payload.get("intervalo_minutos") or mold_state["siguiente_avance_5min"]["intervalo_minutos"],
                "velocidad_real_cm_h": payload.get("velocidad_real_cm_h"),
                "operador": payload.get("operador"),
                "observacion": observation,
                "origen": payload.get("origen") or "manual",
            },
        )

    decision_id = insert_operator_decision(
        conn,
        {
            "colado_id": colado_id,
            "zona_colado_id": (mold_state.get("zona_en_liberacion") or {}).get("id"),
            "avance_molde_id": advance_id,
            "fecha_hora": fecha_hora,
            "recomendacion_sistema": status,
            "decision_operador": decision,
            "conforme_recomendacion": not requires_supervisor,
            "requiere_supervisor": requires_supervisor,
            "operador": payload.get("operador"),
            "supervisor": payload.get("supervisor"),
            "checklist": payload.get("checklist") or {},
            "observacion": observation if wants_early_authorized_advance else payload.get("observacion"),
        },
    )
    updated = get_scada_state(conn, colado_id, as_of_iso=fecha_hora)
    return {"decision_id": decision_id, "avance_molde_id": advance_id, "scada": updated}


def release_zone_by_field_criteria(conn, payload: dict[str, Any]) -> dict[str, Any]:
    colado_id = int(payload["colado_id"])
    fecha_hora = normalize_datetime(payload.get("fecha_hora") or datetime.now().isoformat(timespec="seconds"))
    scada = get_scada_state(conn, colado_id, as_of_iso=fecha_hora)
    mold_state = scada["estado_molde"]
    status = mold_state.get("estado_operativo") or "SIN_DATOS"
    if status in {"MOLDE_INCOMPLETO", "FALTA_ZONA_SUPERIOR", "SIN_ZONA_A_LIBERAR", "SIN_ZONAS"}:
        raise ValueError("No se puede marcar lista por inspeccion: falta completar la informacion fisica del molde.")
    zone = mold_state.get("zona_en_liberacion")
    if not zone or not zone.get("id"):
        raise ValueError("No hay zona proxima a liberar.")
    calculated = float(zone.get("avance_madurez_calculada", zone.get("avance_madurez") or 0.0))
    if calculated >= DEFAULT_PARAMS["slide_threshold"]:
        raise ValueError("La zona ya cumple la madurez calculada; usa el flujo normal de deslizado.")

    checklist = payload.get("checklist") or {}
    if not _checklist_complete(checklist):
        raise ValueError("La liberacion por criterio requiere checklist fisico completo.")
    if not str(payload.get("supervisor") or "").strip():
        raise ValueError("La liberacion por criterio requiere supervisor.")
    if not str(payload.get("motivo") or payload.get("observacion") or "").strip():
        raise ValueError("La liberacion por criterio requiere motivo.")
    if payload.get("temperatura_concreto_c") in (None, ""):
        raise ValueError("La liberacion por criterio requiere temperatura del concreto.")

    release_id = insert_field_release(
        conn,
        {
            "colado_id": colado_id,
            "zona_colado_id": int(zone["id"]),
            "fecha_hora": fecha_hora,
            "madurez_calculada_pct": round(calculated * 100.0, 3),
            "madurez_operativa_pct": 90.0,
            "temperatura_concreto_c": payload.get("temperatura_concreto_c"),
            "temperatura_ambiente_c": payload.get("temperatura_ambiente_c"),
            "humedad_relativa_pct": payload.get("humedad_relativa_pct"),
            "condicion_observada": payload.get("condicion_observada") or payload.get("resultado_fisico"),
            "checklist": checklist,
            "motivo": payload.get("motivo") or payload.get("observacion"),
            "operador": payload.get("operador"),
            "supervisor": payload.get("supervisor"),
        },
    )
    adjustment_id = upsert_field_prediction_adjustment(
        conn,
        {
            "colado_id": colado_id,
            "zona_base_id": int(zone["id"]),
            "fecha_hora": fecha_hora,
            "madurez_calculada_pct": round(calculated * 100.0, 3),
            "temperatura_concreto_c": payload.get("temperatura_concreto_c"),
            "motivo": payload.get("motivo") or payload.get("observacion"),
            "operador": payload.get("operador"),
            "supervisor": payload.get("supervisor"),
        },
    )
    observation = (
        f"LIBERACION POR CRITERIO DE CAMPO. Madurez calculada {calculated * 100.0:.1f}%, "
        "madurez operativa 90.0%. "
        f"Motivo: {payload.get('motivo') or payload.get('observacion') or ''}"
    )
    decision_id = insert_operator_decision(
        conn,
        {
            "colado_id": colado_id,
            "zona_colado_id": int(zone["id"]),
            "avance_molde_id": None,
            "fecha_hora": fecha_hora,
            "recomendacion_sistema": status,
            "decision_operador": "LIBERAR_POR_CRITERIO_CAMPO",
            "conforme_recomendacion": 0,
            "requiere_supervisor": 1,
            "operador": payload.get("operador"),
            "supervisor": payload.get("supervisor"),
            "checklist": checklist,
            "observacion": observation,
        },
    )
    updated = get_scada_state(conn, colado_id, as_of_iso=fecha_hora)
    return {"liberacion_id": release_id, "ajuste_prediccion_id": adjustment_id, "decision_id": decision_id, "scada": updated}


def acknowledge_alarm(conn, payload: dict[str, Any]) -> dict[str, Any]:
    return acknowledge_operational_alarm(conn, payload)


def get_trends(
    conn,
    colado_id: int,
    zona_id: int | None = None,
    rango: str = "4h",
    as_of_iso: str | None = None,
) -> dict[str, Any]:
    mold_state = calculate_mold_state(conn, colado_id, as_of_iso=as_of_iso)
    zone = get_zone(conn, zona_id) if zona_id else mold_state.get("zona_en_liberacion")
    if not zone:
        return {
            "colado_id": colado_id,
            "zona": None,
            "rango": rango,
            "temperatura": {
                "real": [],
                "real_extendida": [],
                "esperada": [],
                "actual": None,
                "diferencia_vs_esperada_c": None,
                "origen_actual": "sin_datos",
            },
            "madurez": {"real": [], "esperada": [], "zonas": []},
            "avance": {"real": [], "objetivo": []},
            "zona_prediccion": _empty_zone_prediction(),
            "resumen_zonas": [],
            "marcadores": _trend_markers(conn, colado_id, None),
        }

    zone = dict(zone)
    as_of = _parse_dt(as_of_iso) if as_of_iso else datetime.now()
    elapsed_min = max(0.0, (as_of - _parse_dt(zone["hora_referencia_madurez"])).total_seconds() / 60.0)
    ref_points = get_reference_points(conn, zone.get("curva_id"))
    actual_temp = _actual_zone_temperature_points(conn, zone)
    actual_maturity = _maturity_points(actual_temp)
    expected = _expected_points(ref_points)
    current_temp = _current_temperature_point(actual_temp, elapsed_min)
    expected_temp = _interpolate_temperature(expected, elapsed_min)
    extended_temp = _extended_temperature_points(actual_temp, current_temp)
    zone_prediction = _zone_maturity_prediction(
        zone,
        actual_temp,
        extended_temp,
        expected,
        as_of,
        latest_active_field_release(conn, int(zone["id"])),
    )
    adjustment = latest_field_prediction_adjustment(conn, colado_id)
    zone_prediction = _with_field_adjusted_prediction(zone_prediction, zone, adjustment, as_of)
    max_minute = _trend_max_minute(zone, extended_temp, as_of.isoformat(timespec="seconds"))
    if zone_prediction.get("minuto_umbral_deslizar") is not None:
        max_minute = max(max_minute, float(zone_prediction["minuto_umbral_deslizar"]))
    if zone_prediction.get("minuto_umbral_deslizar_ajustado") is not None:
        max_minute = max(max_minute, float(zone_prediction["minuto_umbral_deslizar_ajustado"]))
    min_minute = _range_start_minute(max_minute, rango)
    advances = get_advances(conn, colado_id)
    recipe = mold_state.get("receta_avance") or {}
    target_speed = float(recipe.get("velocidad_objetivo_cm_h") or 30)
    expected_temperature_points = [
        {
            "minuto": point["minuto"],
            "temperatura_concreto_c": point["temperatura_concreto_c"],
            "origen": "curva_referencia",
        }
        for point in expected
    ]

    return {
        "colado_id": colado_id,
        "zona": zone,
        "rango": rango,
        "temperatura": {
            "real": _filter_minutes(actual_temp, min_minute, max_minute),
            "real_extendida": _filter_minutes(extended_temp, min_minute, max_minute),
            "esperada": _filter_minutes(expected_temperature_points, min_minute, max_minute),
            "actual": current_temp,
            "diferencia_vs_esperada_c": (
                round(float(current_temp["temperatura_concreto_c"]) - expected_temp, 3)
                if current_temp and expected_temp is not None
                else None
            ),
            "origen_actual": (current_temp or {}).get("origen") or "sin_datos",
        },
        "madurez": {
            "real": _filter_minutes(actual_maturity, min_minute, max_minute),
            "esperada": _filter_minutes(expected, min_minute, max_minute),
            "zonas": [
                {
                    "id": item["id"],
                    "zona_numero": item["zona_numero"],
                    "avance_madurez": item["avance_madurez"],
                    "estado_zona": item["estado_zona"],
                    "elevacion_inferior_cm": item["elevacion_inferior_cm"],
                    "elevacion_superior_cm": item["elevacion_superior_cm"],
                }
                for item in mold_state.get("zonas_activas", [])
            ],
        },
        "avance": {
            "real": advances,
            "objetivo": _target_advance_series(advances, target_speed),
        },
        "umbrales": {"prepararse": 0.70, "deslizar": 0.90, "sobremadurez": 1.05, "critico": 1.15},
        "zona_prediccion": zone_prediction,
        "prediccion_ajustada_campo": _adjustment_payload(adjustment),
        "prediccion_deslizamiento": mold_state.get("prediccion_deslizamiento"),
        "resumen_zonas": _zone_predictions_summary(conn, colado_id, mold_state, as_of),
        "marcadores": _trend_markers(conn, colado_id, int(zone["id"])),
    }


def _alarm(
    colado_id: int,
    zone_id: int | None,
    tipo: str,
    severidad: str,
    mensaje: str,
    fecha_hora: str,
) -> dict[str, Any]:
    return {
        "colado_id": colado_id,
        "zona_colado_id": zone_id,
        "tipo": tipo,
        "severidad": severidad,
        "mensaje": mensaje,
        "fecha_hora_inicio": fecha_hora,
    }


def _scada_label(status: str) -> str:
    if status == "CONTINUAR":
        return "AVANZAR"
    if status in {"NO_LIBERAR", "FALTA_ZONA_SUPERIOR"}:
        return "NO AVANZAR"
    if status == "RIESGO_AGARROTAMIENTO":
        return "RIESGO"
    if status == "PREPARARSE":
        return "PREPARARSE"
    return status.replace("_", " ")


def _actual_zone_temperature_points(conn, zone: dict[str, Any]) -> list[dict[str, Any]]:
    zone_points = [
        {
            "minuto": float(row["minuto_desde_zona"]),
            "temperatura_concreto_c": row.get("temperatura_concreto_c"),
            "temperatura_ambiente_c": row.get("temperatura_ambiente_c"),
            "humedad_relativa_pct": row.get("humedad_relativa_pct"),
            "fecha_hora": row.get("fecha_hora"),
            "origen": row.get("origen") or "manual",
        }
        for row in get_zone_readings(conn, int(zone["id"]))
        if row.get("temperatura_concreto_c") is not None
    ]
    if zone_points:
        return sorted(zone_points, key=lambda item: item["minuto"])

    ref = _parse_dt(zone["hora_referencia_madurez"])
    points = []
    for row in get_readings(conn, int(zone["colado_id"])):
        if row.get("temperatura_concreto_c") is None or not row.get("fecha_hora"):
            continue
        origin = row.get("origen") or "sensor_global"
        if origin == "importacion" and row.get("minuto_transcurrido") is not None:
            minute = float(row["minuto_transcurrido"])
        else:
            minute = (_parse_dt(str(row["fecha_hora"])) - ref).total_seconds() / 60.0
        if minute < 0:
            continue
        points.append(
            {
                "minuto": round(minute, 3),
                "temperatura_concreto_c": row.get("temperatura_concreto_c"),
                "temperatura_ambiente_c": row.get("temperatura_ambiente_c"),
                "humedad_relativa_pct": row.get("humedad_relativa_pct"),
                "fecha_hora": row.get("fecha_hora"),
                "origen": origin,
            }
        )
    if points:
        return sorted(points, key=lambda item: item["minuto"])

    if zone.get("temperatura_inicial_c") is not None:
        return [
            {
                "minuto": 0.0,
                "temperatura_concreto_c": float(zone["temperatura_inicial_c"]),
                "origen": "estimado",
            }
        ]
    return []


def _maturity_points(temp_points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    readings = _dedupe_temp_readings([
        {
            "minuto_transcurrido": point["minuto"],
            "temperatura_concreto_c": point["temperatura_concreto_c"],
        }
        for point in temp_points
        if point.get("temperatura_concreto_c") is not None
    ])
    _maturity, points = calculate_maturity(readings, DEFAULT_PARAMS)
    target = DEFAULT_PARAMS["target_maturity_h_eq"]
    by_minute = {float(item["minuto"]): item for item in temp_points}
    return [
        {
            "minuto": point["minuto"],
            "madurez_arrhenius_h_eq": point["madurez_arrhenius_h_eq"],
            "avance_madurez": point["madurez_arrhenius_h_eq"] / target if target else 0,
            "origen": (by_minute.get(float(point["minuto"])) or {}).get("origen") or "calculado",
        }
        for point in points
    ]


def _dedupe_temp_readings(readings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_minute: dict[float, dict[str, Any]] = {}
    for reading in readings:
        by_minute[float(reading["minuto_transcurrido"])] = reading
    return [by_minute[minute] for minute in sorted(by_minute)]


def _expected_points(reference: list[dict[str, Any]]) -> list[dict[str, Any]]:
    target = DEFAULT_PARAMS["target_maturity_h_eq"]
    sampled = _sample(reference)
    minute_offset = min((float(point.get("minuto") or 0) for point in sampled), default=0.0)
    maturity_offset = min((float(point.get("madurez_arrhenius_h_eq") or 0) for point in sampled), default=0.0)
    return [
        {
            "minuto": float(point["minuto"]) - minute_offset,
            "temperatura_concreto_c": point["temperatura_concreto_c"],
            "madurez_arrhenius_h_eq": max(0.0, float(point["madurez_arrhenius_h_eq"]) - maturity_offset),
            "avance_madurez": max(0.0, float(point["madurez_arrhenius_h_eq"]) - maturity_offset) / target if target else 0,
            "origen": "curva_referencia",
        }
        for point in sampled
    ]


def _current_temperature_point(actual_temp: list[dict[str, Any]], elapsed_min: float) -> dict[str, Any] | None:
    if not actual_temp:
        return None
    previous = [point for point in actual_temp if float(point.get("minuto") or 0) <= elapsed_min]
    base = previous[-1] if previous else actual_temp[0]
    return {
        **base,
        "minuto": round(elapsed_min, 3),
        "temperatura_concreto_c": base.get("temperatura_concreto_c"),
        "origen": _current_origin(str(base.get("origen") or "estimado")),
        "estimado_actual": True,
    }


def _current_origin(origin: str) -> str:
    if origin in {"manual", "sensor", "importacion"}:
        return f"{origin}_mantenida"
    return origin or "estimado"


def _extended_temperature_points(
    actual_temp: list[dict[str, Any]],
    current_temp: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    points = [dict(point) for point in actual_temp]
    if not current_temp:
        return points
    current_minute = float(current_temp.get("minuto") or 0)
    if not points or abs(float(points[-1].get("minuto") or 0) - current_minute) > 0.001:
        points.append(dict(current_temp))
    else:
        points[-1] = {**points[-1], **current_temp}
    return sorted(points, key=lambda item: float(item.get("minuto") or 0))


def _interpolate_temperature(points: list[dict[str, Any]], minute: float) -> float | None:
    ordered = [
        point
        for point in sorted(points, key=lambda item: float(item.get("minuto") or 0))
        if point.get("temperatura_concreto_c") is not None
    ]
    if not ordered:
        return None
    if minute <= float(ordered[0]["minuto"]):
        return float(ordered[0]["temperatura_concreto_c"])
    for previous, current in zip(ordered, ordered[1:]):
        previous_minute = float(previous["minuto"])
        current_minute = float(current["minuto"])
        if previous_minute <= minute <= current_minute and current_minute > previous_minute:
            ratio = (minute - previous_minute) / (current_minute - previous_minute)
            previous_temp = float(previous["temperatura_concreto_c"])
            current_temp = float(current["temperatura_concreto_c"])
            return previous_temp + (current_temp - previous_temp) * ratio
    return float(ordered[-1]["temperatura_concreto_c"])


def _empty_zone_prediction() -> dict[str, Any]:
    return {
        "hora_estimada_deslizar": None,
        "minutos_restantes_deslizar": None,
        "minuto_umbral_deslizar": None,
        "madurez_actual_pct": 0.0,
        "confianza": "insuficiente",
        "desviacion_vs_esperada_min": None,
    }


def _zone_maturity_prediction(
    zone: dict[str, Any],
    actual_temp: list[dict[str, Any]],
    extended_temp: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    as_of: datetime,
    field_release: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not zone.get("hora_referencia_madurez"):
        return _empty_zone_prediction()

    threshold = 0.90
    ref = _parse_dt(str(zone["hora_referencia_madurez"]))
    elapsed_min = max(0.0, (as_of - ref).total_seconds() / 60.0)
    actual_maturity = _maturity_points(extended_temp)
    expected_cross = _threshold_crossing_minute(expected, threshold)
    actual_cross = _threshold_crossing_minute(actual_maturity, threshold)
    if field_release:
        release_dt = _parse_dt(str(field_release["fecha_hora"]))
        release_minute = max(0.0, (release_dt - ref).total_seconds() / 60.0)
        return {
            "zona_id": zone.get("id"),
            "zona_numero": zone.get("zona_numero"),
            "hora_salida_planta": zone.get("hora_salida_planta") or zone.get("hora_referencia_madurez"),
            "edad_actual_h": round(elapsed_min / 60.0, 2),
            "madurez_actual_pct": max(
                float(field_release.get("madurez_operativa_pct") or 90.0),
                _current_maturity_pct(actual_maturity, expected, elapsed_min),
            ),
            "madurez_calculada_pct": field_release.get("madurez_calculada_pct"),
            "hora_estimada_deslizar": release_dt.isoformat(timespec="minutes"),
            "hora_liberacion_campo": release_dt.isoformat(timespec="minutes"),
            "minutos_restantes_deslizar": round((release_dt - as_of).total_seconds() / 60.0, 1),
            "minuto_umbral_deslizar": round(release_minute, 3),
            "confianza": "criterio_campo",
            "desviacion_vs_esperada_min": (
                round(release_minute - float(expected_cross), 1) if expected_cross is not None else None
            ),
            "liberacion_campo": {
                "id": field_release.get("id"),
                "fecha_hora": release_dt.isoformat(timespec="minutes"),
                "madurez_calculada_pct": field_release.get("madurez_calculada_pct"),
                "madurez_operativa_pct": field_release.get("madurez_operativa_pct"),
                "operador": field_release.get("operador"),
                "supervisor": field_release.get("supervisor"),
                "motivo": field_release.get("motivo"),
            },
        }
    has_real_temperature = any(
        str(point.get("origen") or "").split("_")[0] in {"manual", "sensor", "importacion"}
        for point in actual_temp
    )

    minute = actual_cross if has_real_temperature else None
    confidence = "real" if minute is not None else None
    if minute is None and has_real_temperature and actual_maturity and extended_temp:
        minute = _constant_temperature_threshold_minute(actual_maturity, extended_temp, threshold)
        confidence = "mixta"
    if minute is None and expected_cross is not None:
        minute = expected_cross
        confidence = "referencia"
    if minute is None and actual_cross is not None:
        minute = actual_cross
        confidence = "referencia"
    if minute is None and actual_maturity and extended_temp:
        minute = _constant_temperature_threshold_minute(actual_maturity, extended_temp, threshold)
        confidence = "referencia"
    if minute is None:
        result = _empty_zone_prediction()
        result.update(
            {
                "zona_id": zone.get("id"),
                "zona_numero": zone.get("zona_numero"),
                "hora_salida_planta": zone.get("hora_salida_planta") or zone.get("hora_referencia_madurez"),
                "edad_actual_h": round(elapsed_min / 60.0, 2),
                "madurez_actual_pct": _current_maturity_pct(actual_maturity, expected, elapsed_min),
            }
        )
        return result

    estimated_time = ref + timedelta(minutes=float(minute))
    maturity_pct = _current_maturity_pct(actual_maturity, expected, elapsed_min)
    return {
        "zona_id": zone.get("id"),
        "zona_numero": zone.get("zona_numero"),
        "hora_salida_planta": zone.get("hora_salida_planta") or zone.get("hora_referencia_madurez"),
        "edad_actual_h": round(elapsed_min / 60.0, 2),
        "madurez_actual_pct": maturity_pct,
        "hora_estimada_deslizar": estimated_time.isoformat(timespec="minutes"),
        "minutos_restantes_deslizar": round((estimated_time - as_of).total_seconds() / 60.0, 1),
        "minuto_umbral_deslizar": round(float(minute), 3),
        "confianza": confidence or "referencia",
        "desviacion_vs_esperada_min": (
            round(float(minute) - float(expected_cross), 1) if expected_cross is not None else None
        ),
    }


def _with_field_adjusted_prediction(
    prediction: dict[str, Any],
    zone: dict[str, Any],
    adjustment: dict[str, Any] | None,
    as_of: datetime,
) -> dict[str, Any]:
    adjusted = _adjusted_prediction_for_zone(zone, prediction, adjustment, as_of)
    if not adjusted:
        return prediction
    result = dict(prediction)
    result.update(adjusted)
    return result


def _adjusted_prediction_for_zone(
    zone: dict[str, Any],
    prediction: dict[str, Any],
    adjustment: dict[str, Any] | None,
    as_of: datetime,
) -> dict[str, Any] | None:
    if not adjustment:
        return None
    if int(zone.get("zona_numero") or 0) <= int(adjustment.get("zona_base_numero") or 0):
        return None
    plant_departure = zone.get("hora_salida_planta") or zone.get("hora_referencia_madurez")
    if not plant_departure:
        return None
    adjusted_dt = _parse_dt(str(plant_departure)) + timedelta(hours=float(adjustment["edad_observada_liberacion_h"]))
    ref_dt = _parse_dt(str(zone.get("hora_referencia_madurez") or plant_departure))
    arrhenius_dt = _parse_optional_dt(prediction.get("hora_estimada_deslizar"))
    difference = (adjusted_dt - arrhenius_dt).total_seconds() / 60.0 if arrhenius_dt else None
    return {
        "hora_estimada_deslizar_ajustada": adjusted_dt.isoformat(timespec="minutes"),
        "minutos_restantes_deslizar_ajustado": round((adjusted_dt - as_of).total_seconds() / 60.0, 1),
        "minuto_umbral_deslizar_ajustado": round((adjusted_dt - ref_dt).total_seconds() / 60.0, 3),
        "diferencia_ajuste_min": round(difference, 1) if difference is not None else None,
        "prediccion_ajustada_campo": _adjustment_payload(adjustment),
    }


def _parse_optional_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return _parse_dt(str(value))
    except Exception:
        return None


def _adjustment_payload(adjustment: dict[str, Any] | None) -> dict[str, Any] | None:
    if not adjustment:
        return None
    return {
        "id": adjustment.get("id"),
        "zona_base_id": adjustment.get("zona_base_id"),
        "zona_base_numero": adjustment.get("zona_base_numero"),
        "fecha_hora": adjustment.get("fecha_hora"),
        "hora_salida_planta_zona_base": adjustment.get("hora_salida_planta_zona_base"),
        "edad_observada_liberacion_h": adjustment.get("edad_observada_liberacion_h"),
        "madurez_calculada_pct": adjustment.get("madurez_calculada_pct"),
        "temperatura_concreto_c": adjustment.get("temperatura_concreto_c"),
        "motivo": adjustment.get("motivo"),
        "supervisor": adjustment.get("supervisor"),
    }


def _zone_predictions_summary(conn, colado_id: int, mold_state: dict[str, Any], as_of: datetime) -> list[dict[str, Any]]:
    state_by_id = {
        int(item["id"]): item
        for item in [
            *(mold_state.get("zonas_liberadas") or []),
            *(mold_state.get("zonas_activas") or []),
        ]
        if item.get("id") and not str(item.get("id")).startswith("pendiente")
    }
    field_releases_by_zone = {
        int(item["zona_colado_id"]): item
        for item in list_field_releases(conn, colado_id)
        if item.get("zona_colado_id") and int(item.get("activo") or 0) == 1
    }
    adjustment = latest_field_prediction_adjustment(conn, colado_id)
    summary = []
    for zone in get_zones(conn, colado_id):
        if not zone.get("hora_referencia_madurez"):
            continue
        ref_points = get_reference_points(conn, zone.get("curva_id"))
        actual_temp = _actual_zone_temperature_points(conn, zone)
        current = _current_temperature_point(
            actual_temp,
            max(0.0, (as_of - _parse_dt(zone["hora_referencia_madurez"])).total_seconds() / 60.0),
        )
        extended = _extended_temperature_points(actual_temp, current)
        expected = _expected_points(ref_points)
        prediction = _zone_maturity_prediction(
            zone,
            actual_temp,
            extended,
            expected,
            as_of,
            field_releases_by_zone.get(int(zone["id"])),
        )
        prediction = _with_field_adjusted_prediction(prediction, zone, adjustment, as_of)
        state_item = state_by_id.get(int(zone["id"]), {})
        summary.append(
            {
                "id": zone["id"],
                "zona_numero": zone["zona_numero"],
                "numero_olla": None if state_item.get("es_zona_heredada") else zone.get("numero_olla"),
                "es_zona_heredada": bool(state_item.get("es_zona_heredada")),
                "origen_generacion": zone.get("origen_generacion"),
                "elevacion_inferior_cm": zone.get("elevacion_inferior_cm"),
                "elevacion_superior_cm": zone.get("elevacion_superior_cm"),
                "estado_zona": state_item.get("estado_zona") or zone.get("estado"),
                "avance_madurez": state_item.get("avance_madurez"),
                "hora_salida_planta": None if state_item.get("es_zona_heredada") else zone.get("hora_salida_planta") or zone.get("hora_referencia_madurez"),
                "hora_estimada_deslizar": prediction.get("hora_estimada_deslizar"),
                "hora_estimada_deslizar_arrhenius": prediction.get("hora_estimada_deslizar"),
                "hora_estimada_deslizar_ajustada": prediction.get("hora_estimada_deslizar_ajustada"),
                "minutos_restantes_deslizar_ajustado": prediction.get("minutos_restantes_deslizar_ajustado"),
                "diferencia_ajuste_min": prediction.get("diferencia_ajuste_min"),
                "prediccion_ajustada_campo": prediction.get("prediccion_ajustada_campo"),
                "hora_liberacion_campo": prediction.get("hora_liberacion_campo"),
                "minutos_restantes_deslizar": prediction.get("minutos_restantes_deslizar"),
                "madurez_actual_pct": prediction.get("madurez_actual_pct"),
                "madurez_calculada_pct": prediction.get("madurez_calculada_pct"),
                "confianza": prediction.get("confianza"),
                "desviacion_vs_esperada_min": prediction.get("desviacion_vs_esperada_min"),
                "liberacion_campo": prediction.get("liberacion_campo"),
                "madurez_fuente": state_item.get("madurez_fuente") or (
                    "criterio_campo" if prediction.get("liberacion_campo") else "calculada"
                ),
            }
        )
    return summary


def _threshold_crossing_minute(points: list[dict[str, Any]], threshold: float) -> float | None:
    ordered = [
        point
        for point in sorted(points, key=lambda item: float(item.get("minuto") or 0))
        if point.get("avance_madurez") is not None
    ]
    previous_minute = 0.0
    previous_value = 0.0
    for point in ordered:
        minute = float(point.get("minuto") or 0)
        value = float(point.get("avance_madurez") or 0)
        if value >= threshold:
            if value == previous_value:
                return minute
            ratio = (threshold - previous_value) / (value - previous_value)
            return previous_minute + ratio * (minute - previous_minute)
        previous_minute = minute
        previous_value = value
    return None


def _constant_temperature_threshold_minute(
    maturity_points: list[dict[str, Any]],
    temp_points: list[dict[str, Any]],
    threshold: float,
) -> float | None:
    latest_maturity = maturity_points[-1] if maturity_points else None
    latest_temp = temp_points[-1] if temp_points else None
    if not latest_maturity or not latest_temp or latest_temp.get("temperatura_concreto_c") is None:
        return None
    target_h_eq = float(DEFAULT_PARAMS["target_maturity_h_eq"]) * threshold
    current_h_eq = float(latest_maturity.get("madurez_arrhenius_h_eq") or 0)
    latest_minute = float(latest_maturity.get("minuto") or latest_temp.get("minuto") or 0)
    if current_h_eq >= target_h_eq:
        return latest_minute
    factor = arrhenius_factor(float(latest_temp["temperatura_concreto_c"]), DEFAULT_PARAMS)
    if factor <= 0:
        return None
    return latest_minute + ((target_h_eq - current_h_eq) / factor) * 60.0


def _current_maturity_pct(
    actual_maturity: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    elapsed_min: float,
) -> float:
    value = _interpolate_maturity(actual_maturity, elapsed_min)
    if value is None:
        value = _interpolate_maturity(expected, elapsed_min)
    return round(max(0.0, float(value or 0) * 100.0), 1)


def _interpolate_maturity(points: list[dict[str, Any]], minute: float) -> float | None:
    ordered = [
        point
        for point in sorted(points, key=lambda item: float(item.get("minuto") or 0))
        if point.get("avance_madurez") is not None
    ]
    if not ordered:
        return None
    if minute <= float(ordered[0]["minuto"]):
        return float(ordered[0]["avance_madurez"])
    for previous, current in zip(ordered, ordered[1:]):
        previous_minute = float(previous["minuto"])
        current_minute = float(current["minuto"])
        if previous_minute <= minute <= current_minute and current_minute > previous_minute:
            ratio = (minute - previous_minute) / (current_minute - previous_minute)
            return float(previous["avance_madurez"]) + ratio * (
                float(current["avance_madurez"]) - float(previous["avance_madurez"])
            )
    return float(ordered[-1]["avance_madurez"])


def _target_advance_series(advances: list[dict[str, Any]], target_speed_cm_h: float) -> list[dict[str, Any]]:
    minutes = [float(item.get("minuto_transcurrido") or 0) for item in advances]
    max_minute = max([60.0] + minutes)
    return [
        {"minuto_transcurrido": 0.0, "avance_acumulado_cm": 0.0, "origen": "objetivo"},
        {
            "minuto_transcurrido": max_minute,
            "avance_acumulado_cm": (target_speed_cm_h / 60.0) * max_minute,
            "origen": "objetivo",
        },
    ]


def _trend_markers(conn, colado_id: int, zone_id: int | None) -> dict[str, list[dict[str, Any]]]:
    advances = get_advances(conn, colado_id)
    return {
        "eventos": get_events(conn, colado_id),
        "avances": advances,
        "avances_zona": _zone_relative_advances(conn, advances, zone_id),
        "alarmas": list_operational_alarms(conn, colado_id),
        "decisiones": list_operator_decisions(conn, colado_id),
        "liberaciones_campo": list_field_releases(conn, colado_id),
        "ajustes_prediccion_campo": list_field_prediction_adjustments(conn, colado_id),
        "zona_id": zone_id,
    }


def _checklist_complete(checklist: dict[str, Any]) -> bool:
    return all(
        bool(checklist.get(key))
        for key in ("no_desmorona", "no_se_pega", "acabado_aceptable", "sin_arrastre")
    )


def _zone_relative_advances(
    conn,
    advances: list[dict[str, Any]],
    zone_id: int | None,
) -> list[dict[str, Any]]:
    if not zone_id:
        return []
    zone = get_zone(conn, zone_id)
    if not zone or not zone.get("hora_referencia_madurez"):
        return []
    ref = _parse_dt(str(zone["hora_referencia_madurez"]))
    result = []
    for advance in advances:
        if not advance.get("fecha_hora"):
            continue
        minute = (_parse_dt(str(advance["fecha_hora"])) - ref).total_seconds() / 60.0
        if minute < 0:
            continue
        result.append({**advance, "minuto_desde_zona": round(minute, 3)})
    return result


def _trend_max_minute(zone: dict[str, Any], actual: list[dict[str, Any]], as_of_iso: str | None) -> float:
    if as_of_iso:
        elapsed = (_parse_dt(as_of_iso) - _parse_dt(zone["hora_referencia_madurez"])).total_seconds() / 60.0
    else:
        elapsed = 0.0
    values = [elapsed]
    values.extend(float(item.get("minuto") or 0) for item in actual)
    return max([60.0] + values)


def _range_start_minute(max_minute: float, rango: str) -> float:
    if rango in {"4h", "turno", "todo", "all"}:
        return 0.0
    ranges = {"1h": 60.0, "ultima_hora": 60.0, "4h": 240.0, "turno": 720.0}
    return max(0.0, max_minute - ranges.get(rango, 240.0))


def _filter_minutes(points: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    return [point for point in points if start <= float(point.get("minuto") or 0) <= end]


def _sample(points: list[dict[str, Any]], max_points: int = 240) -> list[dict[str, Any]]:
    if len(points) <= max_points:
        return points
    step = max(1, len(points) // max_points)
    return points[::step]


def _parse_dt(value: str) -> datetime:
    return parse_datetime(value)
