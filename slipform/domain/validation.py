"""Pure validation rules shared by repositories and services."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


VALID_READING_ORIGINS = {"manual", "sensor", "importacion", "estimado"}
LOCAL_TIMEZONE = timezone(timedelta(hours=-5), "America/Cancun")


def optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def parse_datetime(value: str) -> datetime:
    text = str(value).strip()
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(LOCAL_TIMEZONE).replace(tzinfo=None)


def normalize_datetime(value: Any, timespec: str = "seconds") -> str:
    return parse_datetime(str(value)).isoformat(timespec=timespec)


def validate_colado_payload(payload: dict[str, Any]) -> None:
    if not payload.get("silo_id"):
        raise ValueError("El colado requiere silo.")
    if payload.get("mezcla_id") in (None, ""):
        raise ValueError("El colado requiere mezcla.")
    ordered = [
        ("hora_salida_planta", "Salida planta"),
        ("hora_llegada_obra", "Llegada obra"),
        ("hora_inicio_descarga", "Inicio descarga"),
        ("hora_colocacion_en_molde", "Colocacion en molde"),
        ("hora_fin_descarga", "Fin descarga"),
    ]
    previous_dt: datetime | None = None
    previous_label = ""
    for key, label in ordered:
        value = payload.get(key)
        if not value:
            continue
        current = parse_datetime(str(value))
        if previous_dt and current < previous_dt:
            raise ValueError(f"{label} no puede ser anterior a {previous_label}.")
        previous_dt = current
        previous_label = label


def validate_origin(origin: str) -> None:
    if origin not in VALID_READING_ORIGINS:
        raise ValueError(f"Origen invalido: {origin}.")


def validate_measurements(payload: dict[str, Any]) -> None:
    concrete = optional_float(payload.get("temperatura_concreto_c"))
    ambient = optional_float(payload.get("temperatura_ambiente_c"))
    humidity = optional_float(payload.get("humedad_relativa_pct"))
    if concrete is None and ambient is None and humidity is None:
        raise ValueError("La lectura requiere al menos temperatura o humedad.")
    validate_range(concrete, -10, 90, "Temperatura de concreto")
    validate_range(ambient, -20, 70, "Temperatura ambiente")
    validate_range(humidity, 0, 100, "Humedad relativa")


def validate_advance_values(payload: dict[str, Any]) -> None:
    advance = optional_float(payload.get("avance_cm"))
    if advance is not None and advance <= 0:
        raise ValueError("El avance debe ser mayor a 0 cm.")
    interval = optional_float(payload.get("intervalo_minutos") or payload.get("intervalo_objetivo_min"))
    if interval is not None and interval <= 0:
        raise ValueError("El intervalo debe ser mayor a 0 minutos.")
    speed = optional_float(payload.get("velocidad_real_cm_h"))
    if speed is not None and speed <= 0:
        raise ValueError("La velocidad real debe ser mayor a 0 cm/h.")
    if payload.get("fecha_hora"):
        parse_datetime(str(payload["fecha_hora"]))


def validate_range(value: float | None, lower: float, upper: float, label: str) -> None:
    if value is None:
        return
    if value < lower or value > upper:
        raise ValueError(f"{label} fuera de rango: {value}.")


__all__ = [
    "VALID_READING_ORIGINS",
    "LOCAL_TIMEZONE",
    "normalize_datetime",
    "optional_float",
    "parse_datetime",
    "validate_advance_values",
    "validate_colado_payload",
    "validate_measurements",
    "validate_origin",
    "validate_range",
]
