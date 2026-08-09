from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .config import DEFAULT_ADVANCE_CM, DEFAULT_ADVANCE_INTERVAL_MIN, DEFAULT_PARAMS
from .core import arrhenius_factor, calculate_maturity
from .domain.validation import parse_datetime
from .db import (
    get_advances,
    get_active_advance_recipe,
    get_colado,
    get_mold_config,
    get_readings,
    get_reference_points,
    get_zone_readings,
    get_zones,
    latest_active_field_release,
    latest_field_prediction_adjustment,
    latest_advance_cm,
)


def calculate_zone_state(
    conn,
    zone: dict[str, Any],
    cfg: dict[str, Any],
    advance_cm: float,
    next_advance_cm: float,
    as_of_iso: str | None = None,
) -> dict[str, Any]:
    as_of = _parse_dt(as_of_iso) if as_of_iso else datetime.now()
    ref = _parse_dt(zone["hora_referencia_madurez"])
    elapsed_min = max(0.0, (as_of - ref).total_seconds() / 60.0)
    target = DEFAULT_PARAMS["target_maturity_h_eq"]
    slide_threshold = DEFAULT_PARAMS["slide_threshold"]
    over_threshold = DEFAULT_PARAMS["over_maturity_threshold"]
    field_release = latest_active_field_release(conn, int(zone["id"]))
    inherited_zone = str(zone.get("origen_generacion") or "").lower() == "existente_previo"

    if inherited_zone and field_release:
        maturity = 0.0
        temp = field_release.get("temperatura_concreto_c")
        source = "criterio_campo"
        ready_delta = 0.0
        over_delta = None
        critical_delta = None
    else:
        maturity, temp, source = _zone_maturity(conn, zone, elapsed_min)
        ready_delta = _minutes_to_threshold(conn, zone, elapsed_min, target * slide_threshold)
        over_delta = _minutes_to_threshold(conn, zone, elapsed_min, target * over_threshold)
        critical_delta = _minutes_to_threshold(conn, zone, elapsed_min, target * DEFAULT_PARAMS["critical_maturity_threshold"])
    calculated_advance_maturity = maturity / target if target else 0.0
    override_maturity = (
        max(0.0, float(field_release.get("madurez_operativa_pct") or 0.0) / 100.0)
        if field_release
        else None
    )
    advance_maturity = max(calculated_advance_maturity, override_maturity or 0.0)
    maturity_source = "criterio_campo" if field_release and advance_maturity > calculated_advance_maturity else "calculada"

    next_exposes_zone = (
        float(zone["elevacion_inferior_cm"]) <= next_advance_cm <= float(zone["elevacion_superior_cm"])
    )
    if advance_cm >= float(zone["elevacion_superior_cm"]):
        state = "LIBERADA"
    elif as_of < _parse_dt(zone["hora_inicio_llenado"]) and not field_release:
        state = "ZONA_EN_LLENADO"
    elif next_exposes_zone and advance_maturity < slide_threshold:
        state = "NO_LIBERAR"
    elif next_exposes_zone and advance_maturity >= over_threshold:
        state = "RIESGO_AGARROTAMIENTO"
    elif next_exposes_zone and advance_maturity >= slide_threshold:
        state = "LIBERABLE"
    elif next_exposes_zone:
        state = "PROXIMA_A_LIBERAR"
    elif elapsed_min / 60.0 >= cfg["residencia_preferente_h"] and advance_maturity < slide_threshold:
        state = "RIESGO_RETARDO"
    else:
        state = "EN_RESIDENCIA"
    if inherited_zone and state != "LIBERADA":
        state = "EXISTENTE_PREVIO"

    return {
        **zone,
        "es_zona_heredada": inherited_zone,
        "edad_real_h": round(elapsed_min / 60.0, 3),
        "madurez_h_eq": round(maturity, 6),
        "avance_madurez_calculada": round(calculated_advance_maturity, 6),
        "avance_madurez_efectiva": round(advance_maturity, 6),
        "avance_madurez": round(advance_maturity, 6),
        "madurez_override_activa": bool(field_release),
        "madurez_override_pct": round(float(field_release.get("madurez_operativa_pct") or 0.0), 3) if field_release else None,
        "madurez_fuente": maturity_source,
        "liberacion_campo": field_release,
        "temperatura_actual_c": temp,
        "fuente_temperatura": source,
        "hora_estimada_lista": _add_minutes(as_of, ready_delta) if ready_delta is not None else None,
        "hora_estimada_sobremadurez": _add_minutes(as_of, over_delta) if over_delta is not None else None,
        "hora_estimada_critico": _add_minutes(as_of, critical_delta) if critical_delta is not None else None,
        "estado_zona": state,
        "es_zona_siguiente": next_exposes_zone,
    }


def _is_inherited_zone(zone: dict[str, Any] | None) -> bool:
    if not zone:
        return False
    return bool(zone.get("es_zona_heredada")) or str(zone.get("origen_generacion") or "").lower() == "existente_previo"


def _apply_control_state(zone: dict[str, Any], *, slide_threshold: float, over_threshold: float) -> dict[str, Any]:
    zone["es_zona_siguiente"] = True
    zone["es_zona_control_operativo"] = True
    if zone.get("pendiente_olla"):
        return zone
    if zone.get("estado_zona") == "LIBERADA":
        return zone
    maturity = float(zone.get("avance_madurez") or 0.0)
    if maturity < slide_threshold:
        zone["estado_zona"] = "NO_LIBERAR"
    elif maturity >= over_threshold:
        zone["estado_zona"] = "RIESGO_AGARROTAMIENTO"
    else:
        zone["estado_zona"] = "LIBERABLE"
    return zone


def _select_operational_control_zone(
    *,
    zone_states: list[dict[str, Any]],
    pending_initial_zones: list[dict[str, Any]],
    window: dict[str, float],
) -> dict[str, Any] | None:
    for zone in zone_states:
        zone["es_zona_siguiente"] = False
        zone["es_zona_control_operativo"] = False

    immediate_zone = next(
        (
            zone
            for zone in zone_states
            if float(zone["elevacion_inferior_cm"]) <= float(window["base_cm"]) + 0.001 < float(zone["elevacion_superior_cm"])
        ),
        None,
    )
    if immediate_zone and not _is_inherited_zone(immediate_zone):
        return _apply_control_state(
            immediate_zone,
            slide_threshold=float(DEFAULT_PARAMS["slide_threshold"]),
            over_threshold=float(DEFAULT_PARAMS["over_maturity_threshold"]),
        )

    candidates = sorted(
        [
            zone
            for zone in zone_states
            if not _is_inherited_zone(zone)
            and float(zone["elevacion_superior_cm"]) > float(window["base_cm"])
            and float(zone["elevacion_inferior_cm"]) < float(window["corona_cm"])
        ],
        key=lambda zone: float(zone["elevacion_inferior_cm"]),
    )
    if candidates:
        return _apply_control_state(
            candidates[0],
            slide_threshold=float(DEFAULT_PARAMS["slide_threshold"]),
            over_threshold=float(DEFAULT_PARAMS["over_maturity_threshold"]),
        )

    pending = sorted(
        [
            zone
            for zone in pending_initial_zones
            if float(zone["elevacion_superior_cm"]) > float(window["base_cm"])
            and float(zone["elevacion_inferior_cm"]) < float(window["corona_cm"])
        ],
        key=lambda zone: float(zone["elevacion_inferior_cm"]),
    )
    if pending:
        pending[0]["es_zona_siguiente"] = True
        pending[0]["es_zona_control_operativo"] = True
        return pending[0]

    return immediate_zone


def calculate_mold_state(conn, colado_id: int, as_of_iso: str | None = None) -> dict[str, Any]:
    colado = get_colado(conn, colado_id)
    if not colado:
        raise ValueError("Colado no encontrado.")
    cfg = get_mold_config(conn)
    recipe = get_active_advance_recipe(conn, colado_id)
    zones = get_zones(conn, colado_id)
    advances = get_advances(conn, colado_id)
    advance_cm = latest_advance_cm(conn, colado_id)
    as_of = _parse_dt(as_of_iso) if as_of_iso else datetime.now()
    next_step = float(recipe["avance_objetivo_cm"])
    next_advance = advance_cm + next_step
    mold_height_cm = float(cfg["altura_molde_m"]) * 100.0
    window = {
        "base_cm": round(advance_cm, 3),
        "corona_cm": round(advance_cm + mold_height_cm, 3),
        "altura_molde_cm": round(mold_height_cm, 3),
    }
    zone_states = [
        calculate_zone_state(conn, zone, cfg, advance_cm, next_advance, as_of_iso)
        for zone in zones
    ]
    required_initial_zones = int(cfg["zonas_por_molde"])
    zone_height_cm = float(cfg["altura_zona_m"]) * 100.0
    physical_start_zone = max(1, int(advance_cm // zone_height_cm) + 1)
    inherited_numbers = sorted(int(zone["zona_numero"]) for zone in zone_states if zone.get("es_zona_heredada"))
    initial_start_zone = min(inherited_numbers) if inherited_numbers else physical_start_zone
    required_zone_numbers = list(range(initial_start_zone, initial_start_zone + required_initial_zones))
    confirmed_initial_count = len([zone for zone in zone_states if int(zone["zona_numero"]) in required_zone_numbers])
    pending_initial_zones = [
        {
            "id": f"pendiente-{number}",
            "zona_numero": number,
            "numero_olla": number,
            "elevacion_inferior_cm": round((number - 1) * zone_height_cm, 3),
            "elevacion_superior_cm": round(number * zone_height_cm, 3),
            "estado_zona": "PENDIENTE_OLLA",
            "estado_olla": "PENDIENTE",
            "pendiente_olla": True,
            "avance_madurez": 0,
            "edad_real_h": 0,
            "madurez_h_eq": 0,
            "temperatura_actual_c": None,
            "fuente_temperatura": "sin_olla",
        }
        for number in required_zone_numbers
        if not any(int(zone["zona_numero"]) == number for zone in zone_states)
    ]
    first_advance = advances[0] if advances else None
    physical_base_initial_cm = (
        float(first_advance["avance_acumulado_cm"])
        if first_advance and first_advance.get("origen") == "arranque_inicial"
        else 0.0
    )
    operational_previous_cm = (max(inherited_numbers) * zone_height_cm) if inherited_numbers else 0.0
    operational_local_cm = max(0.0, float(advance_cm) - physical_base_initial_cm)
    operational_total_cm = operational_previous_cm + operational_local_cm
    operational_release_zone = max(1, int(operational_total_cm // zone_height_cm) + 1)
    operational_fill_zone = max(
        operational_release_zone,
        int((operational_total_cm + mold_height_cm) // zone_height_cm) + 1,
    )
    operational_segment_start = (operational_release_zone - 1) * zone_height_cm
    operational_segment_end = operational_segment_start + zone_height_cm
    operational_segment_progress = max(0.0, min(zone_height_cm, operational_total_cm - operational_segment_start))
    operational_window = {
        "base_cm": round(operational_total_cm, 3),
        "corona_cm": round(operational_total_cm + mold_height_cm, 3),
        "altura_molde_cm": round(mold_height_cm, 3),
    }
    zones_in_mold = [
        zone
        for zone in zone_states
        if float(zone["elevacion_superior_cm"]) > operational_window["base_cm"]
        and float(zone["elevacion_inferior_cm"]) < operational_window["corona_cm"]
    ]
    released_zones = [
        zone for zone in zone_states if float(zone["elevacion_superior_cm"]) <= operational_window["base_cm"]
    ]
    upper_zone = next(
        (
            zone
            for zone in zone_states
            if float(zone["elevacion_inferior_cm"]) <= operational_window["corona_cm"] <= float(zone["elevacion_superior_cm"])
        ),
        zones_in_mold[-1] if zones_in_mold else None,
    )
    next_zone = _select_operational_control_zone(
        zone_states=zone_states,
        pending_initial_zones=pending_initial_zones,
        window=operational_window,
    )
    latest_speed = advances[-1]["velocidad_real_cm_h"] if advances else 0.0
    alerts: list[str] = []
    recommendations: list[str] = []

    if not zones:
        state = "SIN_ZONAS"
        alerts.append("Registra la primera olla para crear la Zona 1.")
    elif confirmed_initial_count < required_initial_zones:
        state = "MOLDE_INCOMPLETO"
        missing = required_initial_zones - confirmed_initial_count
        alerts.append(f"Molde incompleto: faltan {missing} olla(s) para completar los primeros 120 cm.")
        recommendations.append("Registrar la siguiente olla antes de habilitar el deslizado.")
    elif not next_zone:
        state = "SIN_ZONA_A_LIBERAR"
        recommendations.append("Registrar nuevas zonas por encima del avance actual.")
    elif next_zone["estado_zona"] == "NO_LIBERAR":
        state = "NO_LIBERAR"
        alerts.append("El siguiente avance expondría concreto con madurez menor al 90%.")
        recommendations.append("Detener o reducir avance hasta que la zona sea liberable.")
    elif next_zone["estado_zona"] == "RIESGO_AGARROTAMIENTO":
        state = "RIESGO_AGARROTAMIENTO"
        alerts.append("La zona próxima ya supera el umbral de sobremadurez.")
        recommendations.append("Mantener avance y revisar agarrotamiento.")
    elif next_zone["estado_zona"] == "LIBERABLE":
        state = "CONTINUAR"
        recommendations.append(f"Registrar avance de {next_step:.1f} cm si la inspección física es correcta.")
    else:
        state = "PREPARARSE"
        recommendations.append("Mantener monitoreo antes del siguiente avance.")

    min_speed = float(recipe["tolerancia_velocidad_min_cm_h"])
    max_speed = float(recipe["tolerancia_velocidad_max_cm_h"])
    if latest_speed and not (min_speed <= float(latest_speed) <= max_speed):
        alerts.append(
            f"Velocidad real {latest_speed:.1f} cm/h fuera de tolerancia {min_speed:.1f}-{max_speed:.1f} cm/h."
        )
    if zones and (not upper_zone or max(float(zone["elevacion_superior_cm"]) for zone in zone_states) < operational_window["corona_cm"]):
        alerts.append("Falta zona superior para cubrir la ventana actual del molde.")
        if state == "SIN_ZONA_A_LIBERAR":
            state = "FALTA_ZONA_SUPERIOR"

    future_zones = [
        zone
        for zone in zones_in_mold
        if zone.get("hora_referencia_madurez") and _parse_dt(str(zone["hora_referencia_madurez"])) > as_of
    ]
    if future_zones:
        labels = ", ".join(f"Zona {zone['zona_numero']}" for zone in future_zones[:3])
        alerts.append(f"{labels} tiene hora de madurez futura; revisar hora de captura/evaluacion.")

    slide_prediction = _slide_speed_prediction(
        state=state,
        next_zone=next_zone,
        recipe=recipe,
        cfg=cfg,
        advance_cm=operational_total_cm,
        next_step=next_step,
        as_of=as_of,
        confirmed_initial_count=confirmed_initial_count,
        required_initial_zones=required_initial_zones,
    )
    if slide_prediction.get("motivo_recomendacion"):
        recommendations.append(str(slide_prediction["motivo_recomendacion"]))
    field_adjustment = latest_field_prediction_adjustment(conn, colado_id)
    if field_adjustment:
        recommendations.append(
            f"Prediccion ajustada por campo activa desde Zona {field_adjustment.get('zona_base_numero')}."
        )

    return {
        "colado": colado,
        "configuracion_molde": cfg,
        "receta_avance": recipe,
        "hora_evaluacion": as_of.isoformat(timespec="minutes"),
        "ventana_molde": window,
        "base_inicial_cm": round(physical_base_initial_cm, 3),
        "arranque_zona_numero": max(inherited_numbers) + 1 if inherited_numbers else 1,
        "avance_acumulado_cm": round(advance_cm, 3),
        "progreso_operativo": {
            "avance_total_cm": round(operational_total_cm, 3),
            "avance_etapa_cm": round(operational_local_cm, 3),
            "avance_previo_cm": round(operational_previous_cm, 3),
            "base_fisica_cm": round(float(advance_cm), 3),
            "base_inicial_fisica_cm": round(physical_base_initial_cm, 3),
            "zona_liberacion_numero": operational_release_zone,
            "zona_llenado_numero": operational_fill_zone,
            "tramo_inicio_cm": round(operational_segment_start, 3),
            "tramo_fin_cm": round(operational_segment_end, 3),
            "progreso_tramo_cm": round(operational_segment_progress, 3),
            "restante_tramo_cm": round(max(0.0, zone_height_cm - operational_segment_progress), 3),
            "ventana_operativa": operational_window,
        },
        "velocidad_real_cm_h": round(float(latest_speed or 0), 3),
        "zona_en_liberacion": next_zone,
        "zona_superior_en_llenado": upper_zone,
        "zonas_en_molde": zones_in_mold,
        "zonas_liberadas": released_zones,
        "zonas_pendientes_molde": pending_initial_zones,
        "molde_incompleto": confirmed_initial_count < required_initial_zones,
        "zonas_confirmadas_iniciales": confirmed_initial_count,
        "zonas_requeridas_iniciales": required_initial_zones,
        "zonas_requeridas_molde": required_zone_numbers,
        "zonas_activas": zone_states,
        "avances": advances,
        "siguiente_avance_5min": {
            "avance_cm": next_step,
            "intervalo_minutos": float(recipe["intervalo_objetivo_min"]),
            "velocidad_objetivo_cm_h": float(recipe["velocidad_objetivo_cm_h"]),
            "avance_acumulado_cm": round(next_advance, 3),
            "zona_colado_id": next_zone["id"] if next_zone and not next_zone.get("pendiente_olla") else None,
            "permitido": state in ("CONTINUAR", "RIESGO_AGARROTAMIENTO") and confirmed_initial_count >= required_initial_zones,
        },
        "siguiente_avance_receta": {
            "avance_cm": next_step,
            "intervalo_minutos": float(recipe["intervalo_objetivo_min"]),
            "velocidad_objetivo_cm_h": float(recipe["velocidad_objetivo_cm_h"]),
            "avance_acumulado_cm": round(next_advance, 3),
        },
        "estado_operativo": state,
        "alertas": alerts,
        "recomendaciones": recommendations,
        "prediccion_deslizamiento": slide_prediction,
        "prediccion_ajustada_campo": _field_adjustment_payload(field_adjustment),
        "explicacion_operativa": _explain_operation(state, operational_window, next_zone, upper_zone, next_step, latest_speed),
    }


def _field_adjustment_payload(adjustment: dict[str, Any] | None) -> dict[str, Any] | None:
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


def _zone_maturity(conn, zone: dict[str, Any], elapsed_min: float) -> tuple[float, float | None, str]:
    readings = get_zone_readings(conn, int(zone["id"]))
    if readings:
        mapped = [
            {
                "minuto_transcurrido": row["minuto_desde_zona"],
                "temperatura_concreto_c": row["temperatura_concreto_c"],
                "origen": row.get("origen"),
            }
            for row in readings
            if row.get("temperatura_concreto_c") is not None
        ]
        mapped = _dedupe_by_minute(mapped)
        mapped = _extend_last_temperature_to_elapsed(mapped, elapsed_min)
        maturity, points = calculate_maturity(mapped, DEFAULT_PARAMS)
        return maturity, points[-1]["temperatura_concreto_c"] if points else None, _latest_origin(mapped, "zona")

    global_readings = _global_readings_for_zone(conn, zone, elapsed_min)
    if global_readings:
        global_readings = _dedupe_by_minute(global_readings)
        global_readings = _extend_last_temperature_to_elapsed(global_readings, elapsed_min)
        maturity, points = calculate_maturity(global_readings, DEFAULT_PARAMS)
        source = _latest_origin(global_readings, "sensor_global")
        return maturity, points[-1]["temperatura_concreto_c"] if points else None, source

    reference = get_reference_points(conn, zone.get("curva_id"))
    if reference:
        maturity, temp = _reference_maturity_at_elapsed(reference, elapsed_min)
        return maturity, temp, "curva_referencia"

    temp = zone.get("temperatura_inicial_c")
    if temp is None:
        return 0.0, None, "sin_datos"
    maturity = elapsed_min / 60.0 * arrhenius_factor(float(temp), DEFAULT_PARAMS)
    return maturity, float(temp), "estimado"


def _minutes_to_threshold(conn, zone: dict[str, Any], elapsed_min: float, threshold: float) -> float | None:
    current, temp, _source = _zone_maturity(conn, zone, elapsed_min)
    if current >= threshold:
        return 0.0
    reference = get_reference_points(conn, zone.get("curva_id"))
    for point in reference:
        if float(point["minuto"]) >= elapsed_min and float(point["madurez_arrhenius_h_eq"]) >= threshold:
            return max(0.0, float(point["minuto"]) - elapsed_min)
    if temp is None:
        return None
    factor = arrhenius_factor(float(temp), DEFAULT_PARAMS)
    return (threshold - current) / factor * 60.0 if factor > 0 else None


def _reference_maturity_at_elapsed(reference: list[dict[str, Any]], elapsed_min: float) -> tuple[float, float | None]:
    points = [
        {
            "minute": float(point["minuto"]),
            "temp": float(point["temperatura_concreto_c"]),
            "maturity": float(point["madurez_arrhenius_h_eq"]),
        }
        for point in reference
        if point.get("minuto") is not None
        and point.get("temperatura_concreto_c") is not None
        and point.get("madurez_arrhenius_h_eq") is not None
    ]
    points.sort(key=lambda point: point["minute"])
    if not points:
        return 0.0, None

    first = points[0]
    if elapsed_min <= first["minute"]:
        if first["minute"] <= 0:
            return first["maturity"], first["temp"]
        ratio = max(0.0, elapsed_min / first["minute"])
        return first["maturity"] * ratio, first["temp"]

    for previous, current in zip(points, points[1:]):
        if previous["minute"] <= elapsed_min <= current["minute"]:
            span = max(0.001, current["minute"] - previous["minute"])
            ratio = (elapsed_min - previous["minute"]) / span
            maturity = previous["maturity"] + (current["maturity"] - previous["maturity"]) * ratio
            temp = previous["temp"] + (current["temp"] - previous["temp"]) * ratio
            return maturity, temp

    latest = points[-1]
    extra_minutes = max(0.0, elapsed_min - latest["minute"])
    maturity = latest["maturity"] + extra_minutes / 60.0 * arrhenius_factor(latest["temp"], DEFAULT_PARAMS)
    return maturity, latest["temp"]


def _global_readings_for_zone(conn, zone: dict[str, Any], elapsed_min: float) -> list[dict[str, Any]]:
    ref = _parse_dt(zone["hora_referencia_madurez"])
    mapped: list[dict[str, Any]] = []
    for row in get_readings(conn, int(zone["colado_id"])):
        if row.get("temperatura_concreto_c") is None or not row.get("fecha_hora"):
            continue
        minute = (_parse_dt(str(row["fecha_hora"])) - ref).total_seconds() / 60.0
        if 0 <= minute <= elapsed_min:
            item = dict(row)
            item["minuto_transcurrido"] = round(minute, 3)
            mapped.append(item)
    return sorted(mapped, key=lambda item: (float(item["minuto_transcurrido"]), int(item.get("id") or 0)))


def _latest_origin(readings: list[dict[str, Any]], fallback: str) -> str:
    for reading in reversed(readings):
        origin = reading.get("origen")
        if origin:
            return str(origin)
    return fallback


def _extend_last_temperature_to_elapsed(readings: list[dict[str, Any]], elapsed_min: float) -> list[dict[str, Any]]:
    if not readings:
        return readings
    latest = readings[-1]
    latest_min = float(latest["minuto_transcurrido"])
    if elapsed_min <= latest_min + 0.001:
        return readings
    extended = dict(latest)
    extended["minuto_transcurrido"] = round(elapsed_min, 3)
    origin = str(latest.get("origen") or "lectura")
    extended["origen"] = origin if origin.endswith("_mantenida") else f"{origin}_mantenida"
    return [*readings, extended]


def _dedupe_by_minute(readings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_minute: dict[float, dict[str, Any]] = {}
    for reading in readings:
        by_minute[float(reading["minuto_transcurrido"])] = reading
    return [by_minute[minute] for minute in sorted(by_minute)]


def _parse_dt(value: str) -> datetime:
    return parse_datetime(value)


def _add_minutes(base: datetime, minutes: float) -> str:
    return (base + timedelta(minutes=minutes)).isoformat(timespec="minutes")


def _slide_speed_prediction(
    *,
    state: str,
    next_zone: dict[str, Any] | None,
    recipe: dict[str, Any],
    cfg: dict[str, Any],
    advance_cm: float,
    next_step: float,
    as_of: datetime,
    confirmed_initial_count: int,
    required_initial_zones: int,
) -> dict[str, Any]:
    target_speed = float(recipe.get("velocidad_objetivo_cm_h") or cfg.get("velocidad_objetivo_cm_h") or 30.0)
    min_speed = float(recipe.get("tolerancia_velocidad_min_cm_h") or max(0.0, target_speed - 5.0))
    max_speed = float(recipe.get("tolerancia_velocidad_max_cm_h") or target_speed + 5.0)
    blocked_states = {"SIN_ZONAS", "SIN_ZONA_A_LIBERAR", "FALTA_ZONA_SUPERIOR", "MOLDE_INCOMPLETO"}
    base = {
        "zona_control_id": next_zone.get("id") if next_zone else None,
        "zona_control_nombre": f"Zona {next_zone.get('zona_numero')}" if next_zone else None,
        "hora_estimada_90": next_zone.get("hora_estimada_lista") if next_zone else None,
        "hora_estimada_105": next_zone.get("hora_estimada_sobremadurez") if next_zone else None,
        "hora_estimada_115": next_zone.get("hora_estimada_critico") if next_zone else None,
        "minutos_para_90": None,
        "minutos_para_105": None,
        "minutos_para_115": None,
        "velocidad_recomendada_cm_h": None,
        "velocidad_minima_segura_cm_h": None,
        "velocidad_maxima_segura_cm_h": None,
        "velocidad_objetivo_cm_h": round(target_speed, 3),
        "accion_recomendada": "sin_datos",
        "estado_velocidad": "sin_datos",
        "motivo_recomendacion": "Sin zona evaluable para recomendar velocidad.",
        "confianza": "insuficiente",
        "receta_sugerida": None,
    }

    def finish() -> dict[str, Any]:
        return _with_suggested_recipe(base, recipe)

    if state in blocked_states or confirmed_initial_count < required_initial_zones:
        base.update(
            {
                "accion_recomendada": "bloquear",
                "estado_velocidad": "bloqueada",
                "motivo_recomendacion": "No se recomienda velocidad porque el molde o las zonas aun no estan completos.",
            }
        )
        return finish()
    if not next_zone:
        return finish()

    maturity = float(next_zone.get("avance_madurez") or 0.0)
    lower = float(next_zone.get("elevacion_inferior_cm") or 0.0)
    upper = float(next_zone.get("elevacion_superior_cm") or lower + float(cfg.get("altura_zona_m") or 0.30) * 100.0)
    distance_to_first_exposure = max(0.0, lower - float(advance_cm))
    distance_to_full_release = max(0.0, upper - float(advance_cm))
    minutes_90 = _minutes_until(next_zone.get("hora_estimada_lista"), as_of)
    minutes_105 = _minutes_until(next_zone.get("hora_estimada_sobremadurez"), as_of)
    minutes_115 = _minutes_until(next_zone.get("hora_estimada_critico"), as_of)
    max_safe = _speed_for_distance(distance_to_first_exposure, minutes_90)
    min_safe = _speed_for_distance(distance_to_full_release, minutes_105)
    base.update(
        {
            "minutos_para_90": round(minutes_90, 1) if minutes_90 is not None else None,
            "minutos_para_105": round(minutes_105, 1) if minutes_105 is not None else None,
            "minutos_para_115": round(minutes_115, 1) if minutes_115 is not None else None,
            "distancia_para_exponer_cm": round(distance_to_first_exposure, 3),
            "distancia_para_liberar_cm": round(distance_to_full_release, 3),
            "velocidad_minima_segura_cm_h": round(min_safe, 3) if min_safe is not None else None,
            "velocidad_maxima_segura_cm_h": round(max_safe, 3) if max_safe is not None else None,
            "confianza": "estimada" if next_zone.get("hora_estimada_lista") else "insuficiente",
        }
    )

    if maturity < DEFAULT_PARAMS["slide_threshold"]:
        if minutes_90 is None:
            base.update(
            {
                "accion_recomendada": "pausar",
                "estado_velocidad": "pausar",
                "velocidad_recomendada_cm_h": 0.0,
                "motivo_recomendacion": "La zona no tiene estimacion confiable para llegar a 90%; esperar y capturar temperatura.",
            }
        )
            return finish()
        if distance_to_first_exposure <= max(float(next_step), 0.001):
            base.update(
                {
                    "accion_recomendada": "pausar",
                    "estado_velocidad": "pausar",
                    "velocidad_recomendada_cm_h": 0.0,
                    "motivo_recomendacion": f"La zona aun no llega a 90%; faltan {minutes_90:.0f} min antes de liberar.",
                }
            )
            return finish()
        recommended = min(target_speed, max_speed, max_safe if max_safe is not None else target_speed)
        action = "reducir" if recommended < target_speed * 0.95 else "mantener"
        base.update(
            {
                "accion_recomendada": action,
                "estado_velocidad": action,
                "velocidad_recomendada_cm_h": round(max(0.0, recommended), 3),
                "motivo_recomendacion": f"Ajustar velocidad para que la zona alcance 90% antes de exponerse.",
            }
        )
        return finish()

    if maturity >= DEFAULT_PARAMS["critical_maturity_threshold"]:
        base.update(
            {
                "accion_recomendada": "acelerar_con_supervision",
                "estado_velocidad": "critica",
                "velocidad_recomendada_cm_h": round(max_speed, 3),
                "motivo_recomendacion": "La zona supera 115% de madurez; avanzar con supervisor y vigilar agarrotamiento.",
            }
        )
        return finish()

    if maturity >= DEFAULT_PARAMS["over_maturity_threshold"]:
        base.update(
            {
                "accion_recomendada": "acelerar",
                "estado_velocidad": "acelerar",
                "velocidad_recomendada_cm_h": round(max_speed, 3),
                "motivo_recomendacion": "La zona supera 105% de madurez; priorizar avance dentro del limite configurado.",
            }
        )
        return finish()

    if min_safe is not None and min_safe > target_speed:
        recommended = min(max_speed, min_safe)
        base.update(
            {
                "accion_recomendada": "acelerar" if recommended >= min_safe else "acelerar_con_riesgo",
                "estado_velocidad": "acelerar" if recommended >= min_safe else "riesgo",
                "velocidad_recomendada_cm_h": round(recommended, 3),
                "motivo_recomendacion": "Acelerar para liberar la zona antes de superar 105% de madurez.",
            }
        )
        return finish()

    base.update(
        {
            "accion_recomendada": "mantener",
            "estado_velocidad": "mantener",
            "velocidad_recomendada_cm_h": round(min(max(target_speed, min_speed), max_speed), 3),
            "motivo_recomendacion": "La zona esta dentro de ventana segura; mantener la receta actual.",
        }
    )
    return finish()


def _with_suggested_recipe(prediction: dict[str, Any], recipe: dict[str, Any]) -> dict[str, Any]:
    action = str(prediction.get("accion_recomendada") or "")
    speed = prediction.get("velocidad_recomendada_cm_h")
    if action in {"pausar", "bloquear", "sin_datos"} or speed in (None, ""):
        prediction["receta_sugerida"] = None
        return prediction
    speed_value = float(speed)
    if speed_value <= 0:
        prediction["receta_sugerida"] = None
        return prediction

    current_advance = float(recipe.get("avance_objetivo_cm") or DEFAULT_ADVANCE_CM)
    current_interval = float(recipe.get("intervalo_objetivo_min") or DEFAULT_ADVANCE_INTERVAL_MIN)
    suggested_advance = round(max(0.1, speed_value * current_interval / 60.0), 1)
    alternate_interval = round(max(0.1, current_advance / speed_value * 60.0), 1)
    prediction["receta_sugerida"] = {
        "avance_objetivo_cm": suggested_advance,
        "intervalo_objetivo_min": round(current_interval, 1),
        "velocidad_objetivo_cm_h": round(speed_value, 3),
        "tolerancia_velocidad_min_cm_h": round(max(0.0, speed_value - 5.0), 3),
        "tolerancia_velocidad_max_cm_h": round(speed_value + 5.0, 3),
        "avance_actual_cm": round(current_advance, 3),
        "intervalo_alternativo_min": alternate_interval,
        "modo_calculo": "conservar_intervalo",
        "requiere_confirmacion": True,
        "requiere_supervisor": action in {"acelerar_con_supervision", "acelerar_con_riesgo"},
        "motivo": f"Ajuste aplicado desde velocidad recomendada del sistema: {speed_value:.1f} cm/h.",
    }
    return prediction


def _minutes_until(value: Any, as_of: datetime) -> float | None:
    if not value:
        return None
    return (_parse_dt(str(value)) - as_of).total_seconds() / 60.0


def _speed_for_distance(distance_cm: float, minutes: float | None) -> float | None:
    if minutes is None or minutes <= 0:
        return None
    return float(distance_cm) / (float(minutes) / 60.0)


def _explain_operation(
    state: str,
    window: dict[str, float],
    next_zone: dict[str, Any] | None,
    upper_zone: dict[str, Any] | None,
    next_step_cm: float,
    latest_speed: Any,
) -> dict[str, Any]:
    if not next_zone:
        return {
            "titulo": "Generar zonas",
            "resumen": "El molde no tiene una zona inferior evaluable para decidir el siguiente avance.",
            "items": [
                "Genera las zonas iniciales de 30 cm.",
                "Verifica que el colado activo tenga mezcla y curva de referencia.",
            ],
        }
    zone_label = f"Zona {next_zone.get('zona_numero')}"
    upper_label = f"Zona {upper_zone.get('zona_numero')}" if upper_zone else "sin zona superior"
    maturity_pct = float(next_zone.get("avance_madurez") or 0.0) * 100.0
    if state == "NO_LIBERAR":
        title = "No liberar todavia"
        summary = f"El siguiente avance expondria {zone_label}, pero solo tiene {maturity_pct:.1f}% de madurez."
    elif state == "CONTINUAR":
        title = "Avance permitido"
        summary = f"{zone_label} ya es liberable si la inspeccion fisica confirma estabilidad."
    elif state == "RIESGO_AGARROTAMIENTO":
        title = "Riesgo por sobremadurez"
        summary = f"{zone_label} ya supera el umbral alto; avanzar con prioridad y revisar pegado."
    elif state == "PREPARARSE":
        title = "Prepararse"
        summary = f"{zone_label} esta proxima a liberarse; mantener monitoreo antes de mover el molde."
    else:
        title = state.replace("_", " ").title()
        summary = f"El sistema evalua {zone_label} para el siguiente movimiento."
    return {
        "titulo": title,
        "resumen": summary,
        "items": [
            f"Molde entre {window['base_cm']:.1f} y {window['corona_cm']:.1f} cm.",
            f"El siguiente avance es de {next_step_cm:.1f} cm.",
            f"Libera {zone_label} y llena {upper_label}.",
            f"Velocidad real actual: {float(latest_speed or 0):.1f} cm/h.",
        ],
    }
