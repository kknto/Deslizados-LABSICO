"""Data quality rules for operational timestamps and critical corrections."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from slipform.domain.validation import parse_datetime

TIMING_CONFIRM_FLAG = "confirmar_horario_sospechoso"


class DataQualityWarningError(ValueError):
    def __init__(self, warnings: list[dict[str, Any]]):
        super().__init__("Se requiere confirmar horarios sospechosos.")
        self.warnings = warnings


def require_timing_confirmation(
    payload: dict[str, Any],
    *,
    existing_loads: list[dict[str, Any]] | None = None,
    current_load_id: int | str | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    warnings = timing_warnings(payload, existing_loads=existing_loads, current_load_id=current_load_id, now=now)
    if warnings and not _truthy(payload.get(TIMING_CONFIRM_FLAG)):
        raise DataQualityWarningError(warnings)
    return warnings


def timing_warnings(
    payload: dict[str, Any],
    *,
    existing_loads: list[dict[str, Any]] | None = None,
    current_load_id: int | str | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    fields = {
        "hora_salida_planta": _parse_optional(payload.get("hora_salida_planta") or payload.get("t_fabricacion")),
        "hora_llegada_obra": _parse_optional(payload.get("hora_llegada_obra")),
        "hora_inicio_descarga": _parse_optional(payload.get("hora_inicio_descarga")),
        "hora_fin_descarga": _parse_optional(payload.get("hora_fin_descarga")),
    }
    reference_now = now or datetime.now()
    future_limit = reference_now + timedelta(minutes=15)
    for key, value in fields.items():
        if value and value > future_limit:
            warnings.append(_warning("HORA_FUTURA", key, f"{_label(key)} esta en el futuro.", value=payload.get(key) or payload.get("t_fabricacion")))

    _add_chronology_warning(warnings, fields, payload, "hora_salida_planta", "hora_llegada_obra")
    _add_chronology_warning(warnings, fields, payload, "hora_llegada_obra", "hora_inicio_descarga")
    _add_chronology_warning(warnings, fields, payload, "hora_inicio_descarga", "hora_fin_descarga")
    _add_sequence_warnings(warnings, payload, existing_loads or [], current_load_id)
    return warnings


def build_data_quality_report(conn, colado_id: int) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    loads = [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM descargas_olla
            WHERE colado_id = ?
            ORDER BY CAST(numero_olla AS INTEGER), id
            """,
            (colado_id,),
        ).fetchall()
    ]
    zones = [
        dict(row)
        for row in conn.execute(
            """
            SELECT z.*, d.numero_olla
            FROM zonas_colado z
            LEFT JOIN descargas_olla d ON d.id = z.descarga_olla_id
            WHERE z.colado_id = ?
            ORDER BY z.zona_numero
            """,
            (colado_id,),
        ).fetchall()
    ]
    for load in loads:
        for warning in timing_warnings(load, existing_loads=loads, current_load_id=load.get("id")):
            issues.append(_issue_from_warning(warning, "descargas_olla", load.get("id"), load.get("numero_olla")))
    for zone in zones:
        inherited = str(zone.get("origen_generacion") or "").lower() == "existente_previo"
        if not inherited and not zone.get("hora_salida_planta"):
            issues.append(
                {
                    "level": "critical",
                    "code": "ZONA_SIN_SALIDA_PLANTA",
                    "entity": "zonas_colado",
                    "entity_id": zone.get("id"),
                    "label": f"Zona {zone.get('zona_numero')}",
                    "message": f"Zona {zone.get('zona_numero')} sin salida de planta.",
                }
            )
    critical = len([item for item in issues if item["level"] == "critical"])
    warnings = len([item for item in issues if item["level"] == "warn"])
    status = "critical" if critical else "warn" if warnings else "ok"
    summary = (
        "Sin alertas de datos."
        if status == "ok"
        else f"{critical} critico(s), {warnings} aviso(s) de calidad de datos."
    )
    return {"status": status, "summary": summary, "issues": issues, "counts": {"critical": critical, "warn": warnings}}


def _add_chronology_warning(
    warnings: list[dict[str, Any]],
    fields: dict[str, datetime | None],
    payload: dict[str, Any],
    first: str,
    second: str,
) -> None:
    first_dt = fields.get(first)
    second_dt = fields.get(second)
    if not first_dt or not second_dt or second_dt >= first_dt:
        return
    warnings.append(
        _warning(
            "HORARIO_FUERA_DE_ORDEN",
            second,
            f"{_label(second)} es anterior a {_label(first)}.",
            value=payload.get(second),
        )
    )


def _add_sequence_warnings(
    warnings: list[dict[str, Any]],
    payload: dict[str, Any],
    existing_loads: list[dict[str, Any]],
    current_load_id: int | str | None,
) -> None:
    number = _optional_int(payload.get("numero_olla"))
    departure = _parse_optional(payload.get("hora_salida_planta"))
    if number is None or departure is None:
        return
    current = str(current_load_id or payload.get("id") or "")
    loads = []
    for load in existing_loads:
        if current and str(load.get("id") or "") == current:
            continue
        load_number = _optional_int(load.get("numero_olla"))
        load_departure = _parse_optional(load.get("hora_salida_planta"))
        if load_number is not None and load_departure is not None:
            loads.append({"number": load_number, "departure": load_departure})
    previous = sorted([item for item in loads if item["number"] < number], key=lambda item: item["number"], reverse=True)
    next_items = sorted([item for item in loads if item["number"] > number], key=lambda item: item["number"])
    if previous and departure < previous[0]["departure"]:
        warnings.append(
            _warning("OLLA_FUERA_DE_SECUENCIA", "hora_salida_planta", f"Olla {number} sale antes que Olla {previous[0]['number']}.")
        )
    if next_items and departure > next_items[0]["departure"]:
        warnings.append(
            _warning("OLLA_FUERA_DE_SECUENCIA", "hora_salida_planta", f"Olla {number} sale despues que Olla {next_items[0]['number']}.")
        )


def _issue_from_warning(warning: dict[str, Any], entity: str, entity_id: Any, load_number: Any) -> dict[str, Any]:
    level = "critical" if warning["code"] in {"HORA_FUTURA", "HORARIO_FUERA_DE_ORDEN"} else "warn"
    return {
        "level": level,
        "code": warning["code"],
        "field": warning.get("field"),
        "entity": entity,
        "entity_id": entity_id,
        "label": f"Olla {load_number}",
        "message": f"Olla {load_number}: {warning['message']}",
    }


def _warning(code: str, field: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "field": field, "message": message, **extra}


def _parse_optional(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return parse_datetime(str(value))


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


def _label(name: str) -> str:
    return {
        "hora_salida_planta": "Salida planta",
        "hora_llegada_obra": "Llegada obra",
        "hora_inicio_descarga": "Inicio descarga",
        "hora_fin_descarga": "Fin descarga",
    }.get(name, name)


__all__ = [
    "DataQualityWarningError",
    "TIMING_CONFIRM_FLAG",
    "build_data_quality_report",
    "require_timing_confirmation",
    "timing_warnings",
]
