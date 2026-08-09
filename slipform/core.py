from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from .config import DEFAULT_PARAMS


def arrhenius_factor(temp_c: float, params: dict[str, float] | None = None) -> float:
    cfg = DEFAULT_PARAMS | (params or {})
    temp_k = temp_c + 273.15
    ref_k = cfg["t_ref_c"] + 273.15
    return math.exp(
        -cfg["activation_energy_j_mol"]
        / cfg["gas_constant_j_mol_k"]
        * (1 / temp_k - 1 / ref_k)
    )


def calculate_maturity(
    readings: list[dict[str, Any]], params: dict[str, float] | None = None
) -> tuple[float, list[dict[str, float]]]:
    valid = _valid_concrete_readings(readings, params)
    if not valid:
        return 0.0, []

    points: list[dict[str, float]] = []
    maturity = 0.0
    prev_minute: float | None = None
    prev_temp: float | None = None

    for reading in valid:
        minute = float(reading["minuto_transcurrido"])
        temp = float(reading["temperatura_concreto_c"])
        if prev_minute is None:
            dt_hours = max(0.0, minute / 60.0)
            factor = arrhenius_factor(temp, params)
        else:
            dt_hours = (minute - prev_minute) / 60.0
            if dt_hours <= 0:
                raise ValueError("Las lecturas deben tener minutos crecientes.")
            factor = arrhenius_factor((temp + float(prev_temp)) / 2.0, params)

        maturity += dt_hours * factor
        points.append(
            {
                "minuto": minute,
                "temperatura_concreto_c": temp,
                "factor_arrhenius": factor,
                "madurez_arrhenius_h_eq": maturity,
            }
        )
        prev_minute = minute
        prev_temp = temp

    return maturity, points


def calculate_state(
    readings: list[dict[str, Any]],
    params: dict[str, float] | None = None,
    reference_points: list[dict[str, Any]] | None = None,
    now_iso: str | None = None,
) -> dict[str, Any]:
    cfg = DEFAULT_PARAMS | (params or {})
    alerts: list[str] = []
    sensor_status = "OK"

    invalid_reasons = validate_readings(readings, cfg, now_iso=now_iso)
    if invalid_reasons:
        sensor_status = "INVALIDO"
        alerts.extend(invalid_reasons)

    concrete_readings = _valid_concrete_readings(readings, cfg)
    if not concrete_readings:
        return {
            "madurez_acumulada_h_eq": 0.0,
            "avance": 0.0,
            "estado": "SIN_DATOS" if not invalid_reasons else "SENSOR_INVALIDO",
            "minutos_estimados_restantes": None,
            "temperatura_actual_concreto_c": None,
            "temperatura_ambiente_c": None,
            "humedad_relativa_pct": None,
            "desviacion_vs_laboratorio": None,
            "alertas": alerts,
            "sensor_status": sensor_status,
            "puntos_madurez": [],
        }

    maturity_readings = _deduplicate_by_minute(concrete_readings)
    try:
        maturity, points = calculate_maturity(maturity_readings, cfg)
    except ValueError as exc:
        sensor_status = "INVALIDO"
        alerts.append(str(exc))
        latest = concrete_readings[-1]
        return {
            "madurez_acumulada_h_eq": 0.0,
            "avance": 0.0,
            "estado": "SENSOR_INVALIDO",
            "minutos_estimados_restantes": None,
            "temperatura_actual_concreto_c": float(latest["temperatura_concreto_c"]),
            "temperatura_ambiente_c": _last_number(concrete_readings, "temperatura_ambiente_c"),
            "humedad_relativa_pct": _last_number(concrete_readings, "humedad_relativa_pct"),
            "desviacion_vs_laboratorio": None,
            "alertas": sorted(set(alerts)),
            "sensor_status": sensor_status,
            "puntos_madurez": [],
        }
    latest = concrete_readings[-1]
    target = cfg["target_maturity_h_eq"]
    advance = maturity / target if target > 0 else 0.0
    latest_factor = arrhenius_factor(float(latest["temperatura_concreto_c"]), cfg)
    remaining = max(0.0, (target - maturity) / latest_factor * 60.0)
    deviation = _deviation_from_reference(points[-1]["minuto"], maturity, reference_points, target)

    if invalid_reasons:
        state = "SENSOR_INVALIDO"
    elif deviation is not None and deviation < -0.15 and advance < cfg["slide_threshold"]:
        state = "RIESGO_RETARDO"
        alerts.append("Madurez por debajo de la curva de laboratorio de referencia.")
    elif advance < cfg["prepare_threshold"]:
        state = "ESPERAR"
    elif advance < cfg["slide_threshold"]:
        state = "PREPARARSE"
    elif advance <= cfg["over_maturity_threshold"]:
        state = "DESLIZAR"
    elif advance <= cfg["critical_maturity_threshold"]:
        state = "RIESGO_AGARROTAMIENTO"
    else:
        state = "CRITICO"

    return {
        "madurez_acumulada_h_eq": round(maturity, 6),
        "avance": round(advance, 6),
        "estado": state,
        "minutos_estimados_restantes": round(remaining, 2),
        "temperatura_actual_concreto_c": float(latest["temperatura_concreto_c"]),
        "temperatura_ambiente_c": _last_number(concrete_readings, "temperatura_ambiente_c"),
        "humedad_relativa_pct": _last_number(concrete_readings, "humedad_relativa_pct"),
        "desviacion_vs_laboratorio": deviation,
        "alertas": sorted(set(alerts)),
        "sensor_status": sensor_status,
        "puntos_madurez": points,
    }


def validate_readings(
    readings: list[dict[str, Any]],
    params: dict[str, float] | None = None,
    now_iso: str | None = None,
) -> list[str]:
    cfg = DEFAULT_PARAMS | (params or {})
    reasons: list[str] = []
    usable = [r for r in readings if r.get("temperatura_concreto_c") not in (None, "")]
    if not usable:
        return reasons

    prev_minute: float | None = None
    for reading in sorted(usable, key=lambda r: float(r.get("minuto_transcurrido") or 0)):
        minute = _number(reading.get("minuto_transcurrido"))
        concrete_temp = _number(reading.get("temperatura_concreto_c"))
        ambient_temp = _number(reading.get("temperatura_ambiente_c"))
        humidity = _number(reading.get("humedad_relativa_pct"))

        if minute is None or minute < 0:
            reasons.append("Minuto transcurrido inválido.")
        if concrete_temp is None or not (
            cfg["min_concrete_temp_c"] <= concrete_temp <= cfg["max_concrete_temp_c"]
        ):
            reasons.append("Temperatura del concreto fuera de rango.")
        if ambient_temp is not None and not (
            cfg["min_ambient_temp_c"] <= ambient_temp <= cfg["max_ambient_temp_c"]
        ):
            reasons.append("Temperatura ambiental fuera de rango.")
        if humidity is not None and not (0 <= humidity <= 100):
            reasons.append("Humedad relativa fuera de rango.")
        if prev_minute is not None and minute is not None and minute <= prev_minute:
            reasons.append("Lecturas duplicadas o con minutos no crecientes.")
        prev_minute = minute

    if now_iso:
        latest = max(usable, key=lambda r: str(r.get("fecha_hora") or ""))
        if latest.get("origen") == "sensor" and latest.get("fecha_hora"):
            age = _minutes_between(str(latest["fecha_hora"]), now_iso)
            if age is not None and age > cfg["max_sensor_gap_minutes"]:
                reasons.append("Lectura automática vencida por más de 10 minutos.")

    return sorted(set(reasons))


def _valid_concrete_readings(
    readings: list[dict[str, Any]], params: dict[str, float] | None = None
) -> list[dict[str, Any]]:
    cfg = DEFAULT_PARAMS | (params or {})
    clean = []
    for reading in readings:
        minute = _number(reading.get("minuto_transcurrido"))
        temp = _number(reading.get("temperatura_concreto_c"))
        if minute is None or temp is None:
            continue
        if minute < 0 or not (cfg["min_concrete_temp_c"] <= temp <= cfg["max_concrete_temp_c"]):
            continue
        item = dict(reading)
        item["minuto_transcurrido"] = minute
        item["temperatura_concreto_c"] = temp
        clean.append(item)
    return sorted(clean, key=lambda r: float(r["minuto_transcurrido"]))


def _deduplicate_by_minute(readings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_minute: dict[float, dict[str, Any]] = {}
    for reading in readings:
        by_minute[float(reading["minuto_transcurrido"])] = reading
    return [by_minute[minute] for minute in sorted(by_minute)]


def _deviation_from_reference(
    minute: float,
    maturity: float,
    reference_points: list[dict[str, Any]] | None,
    target: float,
) -> float | None:
    if not reference_points:
        return None
    points = sorted(
        [
            (float(p["minuto"]), float(p["madurez_arrhenius_h_eq"]))
            for p in reference_points
            if p.get("minuto") is not None and p.get("madurez_arrhenius_h_eq") is not None
        ]
    )
    if not points:
        return None
    expected = _interpolate(points, minute)
    if expected is None or target <= 0:
        return None
    return round((maturity - expected) / target, 6)


def _interpolate(points: list[tuple[float, float]], x: float) -> float | None:
    if x <= points[0][0]:
        return points[0][1]
    for index in range(1, len(points)):
        x0, y0 = points[index - 1]
        x1, y1 = points[index]
        if x <= x1:
            if x1 == x0:
                return y1
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def _last_number(readings: list[dict[str, Any]], key: str) -> float | None:
    for reading in reversed(readings):
        value = _number(reading.get(key))
        if value is not None:
            return value
    return None


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _minutes_between(start_iso: str, end_iso: str) -> float | None:
    try:
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return (end - start).total_seconds() / 60.0
    except ValueError:
        return None
