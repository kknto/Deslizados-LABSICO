"""Slipform schedule calculation from cylinder test scenarios."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

SCENARIOS: dict[str, dict[str, Any]] = {
    "SCENARIO_4H": {
        "label": "4h",
        "test_hour": 4,
        "step_cm": 3.0,
        "step_minutes": 8.0,
        "status": "Cilindro paso a 4h",
    },
    "SCENARIO_5H": {
        "label": "5h",
        "test_hour": 5,
        "step_cm": 3.0,
        "step_minutes": 10.0,
        "status": "Cilindro paso a 5h",
    },
    "SCENARIO_6H": {
        "label": "6h",
        "test_hour": 6,
        "step_cm": 3.0,
        "step_minutes": 12.0,
        "status": "Cilindro paso a 6h",
    },
}

PENDING = "PENDIENTE"
PASS = "PASA"
FAIL = "FALLA"


def normalize_result(value: Any) -> str:
    raw = str(value or "").strip().upper()
    aliases = {
        "": PENDING,
        "PENDIENTE": PENDING,
        "PENDING": PENDING,
        "PASA": PASS,
        "PASO": PASS,
        "PASS": PASS,
        "OK": PASS,
        "FALLA": FAIL,
        "FALLO": FAIL,
        "FAIL": FAIL,
        "NO": FAIL,
    }
    if raw not in aliases:
        raise ValueError("Resultado de cilindro no valido.")
    return aliases[raw]


def resolve_cylinder_scenario(results: dict[str, Any]) -> dict[str, Any]:
    result_4h = normalize_result(results.get("resultado_4h"))
    result_5h = normalize_result(results.get("resultado_5h"))
    result_6h = normalize_result(results.get("resultado_6h"))

    if result_4h == PASS:
        return _scenario_status("SCENARIO_4H", "ACTIVO")
    if result_4h == PENDING:
        if result_5h != PENDING or result_6h != PENDING:
            raise ValueError("Registra primero el resultado del cilindro a 4h.")
        return _waiting_status("ENSAYO_4H_PENDIENTE", "Esperar resultado de cilindro 4h.")
    if result_5h == PASS:
        return _scenario_status("SCENARIO_5H", "ACTIVO")
    if result_5h == PENDING:
        if result_6h != PENDING:
            raise ValueError("Registra primero el resultado del cilindro a 5h.")
        return _waiting_status("ENSAYO_5H_PENDIENTE", "Cilindro 4h no liberable; esperar 5h.")
    if result_6h == PASS:
        return _scenario_status("SCENARIO_6H", "ACTIVO")
    if result_6h == PENDING:
        return _waiting_status("ENSAYO_6H_PENDIENTE", "Cilindro 5h no liberable; esperar 6h.")
    return {
        "escenario_activo": None,
        "estado": "REQUIERE_SUPERVISOR",
        "alerta": "ENSAYO_6H_FALLA_SUPERVISOR",
        "mensaje": "Cilindro 6h no liberable; requiere supervisor.",
        "receta_sugerida": None,
    }


def calculate_slipform_schedule(
    start_time: str,
    scenario: str,
    layer_thickness_cm: float = 30.0,
    total_layers: int = 7,
    start_zone: int = 1,
) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise ValueError("Escenario de cilindro no valido.")
    if layer_thickness_cm <= 0:
        raise ValueError("El espesor de capa debe ser mayor a cero.")
    if total_layers <= 0:
        raise ValueError("El total de capas debe ser mayor a cero.")
    if start_zone <= 0:
        raise ValueError("La zona inicial debe ser mayor a cero.")
    if start_zone > total_layers:
        raise ValueError("La zona inicial no puede ser mayor al total de capas.")

    start_dt = parse_datetime(start_time)
    cfg = SCENARIOS[scenario]
    interval_minutes = float(layer_thickness_cm) * (float(cfg["step_minutes"]) / float(cfg["step_cm"]))
    speed_cm_min = float(cfg["step_cm"]) / float(cfg["step_minutes"])
    layers = []
    for index, zone_number in enumerate(range(int(start_zone), int(total_layers) + 1)):
        target_dt = start_dt + timedelta(minutes=interval_minutes * index)
        layers.append(
            {
                "capa": zone_number,
                "zona_numero": zone_number,
                "hora_programada": target_dt.isoformat(timespec="minutes"),
                "offset_min": round(interval_minutes * index, 2),
                "offset_texto": _offset_text(interval_minutes * index),
            }
        )
    return {
        "escenario": scenario,
        "escenario_label": cfg["label"],
        "t_fabricacion": start_dt.isoformat(timespec="minutes"),
        "step_cm": float(cfg["step_cm"]),
        "step_minutes": float(cfg["step_minutes"]),
        "layer_thickness_cm": float(layer_thickness_cm),
        "total_layers": int(total_layers),
        "start_zone": int(start_zone),
        "layer_interval_minutes": round(interval_minutes, 2),
        "speed_cm_min": round(speed_cm_min, 6),
        "speed_cm_h": round(speed_cm_min * 60.0, 3),
        "receta_sugerida": {
            "avance_objetivo_cm": float(cfg["step_cm"]),
            "intervalo_objetivo_min": float(cfg["step_minutes"]),
            "velocidad_objetivo_cm_h": round(speed_cm_min * 60.0, 3),
            "tolerancia_velocidad_min_cm_h": max(0.0, round(speed_cm_min * 60.0 - 5.0, 3)),
            "tolerancia_velocidad_max_cm_h": round(speed_cm_min * 60.0 + 5.0, 3),
            "modo_calculo": "ensayo_cilindro",
            "requiere_confirmacion": True,
            "motivo": f"Receta sugerida por ensayo de cilindro {cfg['label']}.",
        },
        "capas": layers,
    }


def parse_datetime(value: str) -> datetime:
    if not value:
        raise ValueError("La hora de fabricacion es requerida.")
    normalized = str(value).strip().replace(" ", "T")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("Fecha/hora invalida.") from exc


def _scenario_status(scenario: str, estado: str) -> dict[str, Any]:
    schedule = SCENARIOS[scenario]
    speed = float(schedule["step_cm"]) / float(schedule["step_minutes"]) * 60.0
    return {
        "escenario_activo": scenario,
        "estado": estado,
        "alerta": "PROGRAMA_RECALCULADO_POR_CILINDRO",
        "mensaje": schedule["status"],
        "receta_sugerida": {
            "avance_objetivo_cm": float(schedule["step_cm"]),
            "intervalo_objetivo_min": float(schedule["step_minutes"]),
            "velocidad_objetivo_cm_h": round(speed, 3),
            "tolerancia_velocidad_min_cm_h": max(0.0, round(speed - 5.0, 3)),
            "tolerancia_velocidad_max_cm_h": round(speed + 5.0, 3),
            "modo_calculo": "ensayo_cilindro",
            "requiere_confirmacion": True,
            "motivo": f"Receta sugerida por ensayo de cilindro {schedule['label']}.",
        },
    }


def _waiting_status(alerta: str, mensaje: str) -> dict[str, Any]:
    return {
        "escenario_activo": None,
        "estado": "ESPERANDO_ENSAYO",
        "alerta": alerta,
        "mensaje": mensaje,
        "receta_sugerida": None,
    }


def _offset_text(minutes: float) -> str:
    total = int(round(minutes))
    hours, mins = divmod(total, 60)
    return f"+{hours}:{mins:02d}"


__all__ = [
    "FAIL",
    "PASS",
    "PENDING",
    "SCENARIOS",
    "calculate_slipform_schedule",
    "normalize_result",
    "resolve_cylinder_scenario",
]
