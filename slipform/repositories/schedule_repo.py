"""Repository helpers for cylinder-test slipform schedules."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from slipform.domain.slip_schedule import calculate_slipform_schedule, normalize_result, resolve_cylinder_scenario


def save_cylinder_test_schedule(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    colado_id = int(payload["colado_id"])
    if not conn.execute("SELECT 1 FROM colados WHERE id = ?", (colado_id,)).fetchone():
        raise ValueError("Colado no encontrado.")
    start_time = _required_text(payload.get("t_fabricacion") or payload.get("hora_salida_planta"))
    layer_thickness = float(payload.get("layer_thickness_cm") or payload.get("espesor_capa_cm") or 30.0)
    total_layers = int(payload.get("total_layers") or payload.get("total_capas") or 7)
    start_zone = int(payload.get("start_zone") or payload.get("zona_inicial") or 1)
    results = {
        "resultado_4h": normalize_result(payload.get("resultado_4h")),
        "resultado_5h": normalize_result(payload.get("resultado_5h")),
        "resultado_6h": normalize_result(payload.get("resultado_6h")),
    }
    scenario_status = resolve_cylinder_scenario(results)
    scenario = scenario_status.get("escenario_activo")
    now = _normalize_dt(payload.get("fecha_hora") or datetime.now().isoformat(timespec="seconds"))

    values = (
        colado_id,
        start_time,
        results["resultado_4h"] or "PENDIENTE",
        _normalize_dt(payload.get("fecha_hora_4h")) if results["resultado_4h"] else None,
        results["resultado_5h"] or "PENDIENTE",
        _normalize_dt(payload.get("fecha_hora_5h")) if results["resultado_5h"] else None,
        results["resultado_6h"] or "PENDIENTE",
        _normalize_dt(payload.get("fecha_hora_6h")) if results["resultado_6h"] else None,
        scenario,
        scenario_status["estado"],
        payload.get("operador"),
        payload.get("supervisor"),
        payload.get("observaciones"),
        now,
        layer_thickness,
        total_layers,
        start_zone,
    )
    row = conn.execute(
        """
        INSERT INTO ensayos_cilindro_deslizamiento(
            colado_id, t_fabricacion, resultado_4h, fecha_hora_4h,
            resultado_5h, fecha_hora_5h, resultado_6h, fecha_hora_6h,
            escenario_activo, estado, operador, supervisor, observaciones,
            updated_at, layer_thickness_cm, total_layers, start_zone
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        values,
    ).fetchone()
    ensayo_id = int(row["id"])

    if scenario:
        conn.execute(
            """
            UPDATE programas_deslizado
            SET activo = 0
            WHERE colado_id = ? AND start_zone >= ?
            """,
            (colado_id, start_zone),
        )
        schedule = calculate_slipform_schedule(start_time, scenario, layer_thickness, total_layers, start_zone)
        row = conn.execute(
            """
            INSERT INTO programas_deslizado(
                colado_id, ensayo_cilindro_id, t_fabricacion, escenario,
                step_cm, step_minutes, layer_thickness_cm, total_layers,
                start_zone, layer_interval_minutes, speed_cm_min, speed_cm_h,
                activo, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            RETURNING id
            """,
            (
                colado_id,
                ensayo_id,
                schedule["t_fabricacion"],
                scenario,
                schedule["step_cm"],
                schedule["step_minutes"],
                schedule["layer_thickness_cm"],
                schedule["total_layers"],
                schedule["start_zone"],
                schedule["layer_interval_minutes"],
                schedule["speed_cm_min"],
                schedule["speed_cm_h"],
                now,
            ),
        ).fetchone()
        programa_id = int(row["id"])
        for layer in schedule["capas"]:
            conn.execute(
                """
                INSERT INTO programas_deslizado_capas(
                    programa_id, capa_numero, zona_numero, hora_programada,
                    offset_min, estado
                )
                VALUES (?, ?, ?, ?, ?, 'PROGRAMADA')
                """,
                (programa_id, layer["capa"], layer["zona_numero"], layer["hora_programada"], layer["offset_min"]),
            )

    conn.commit()
    return get_cylinder_test_schedule(conn, colado_id)


def get_cylinder_test_schedule(
    conn: sqlite3.Connection,
    colado_id: int,
    *,
    include_layers: bool = True,
) -> dict[str, Any]:
    ensayo_rows = conn.execute(
        """
        SELECT *
        FROM ensayos_cilindro_deslizamiento
        WHERE colado_id = ?
        ORDER BY id
        """,
        (colado_id,),
    ).fetchall()
    programa_rows = conn.execute(
        """
        SELECT *
        FROM programas_deslizado
        WHERE colado_id = ? AND activo = 1
        ORDER BY start_zone, id
        """,
        (colado_id,),
    ).fetchall()
    ensayo = ensayo_rows[-1] if ensayo_rows else None
    programa = max(programa_rows, key=lambda row: int(row["id"])) if programa_rows else None
    result: dict[str, Any] = {
        "ensayo": dict(ensayo) if ensayo else None,
        "programa": dict(programa) if programa else None,
        "historial": [_revision_dict(row) for row in ensayo_rows],
        "programas": [dict(row) for row in programa_rows],
        "capas": [],
        "resumen": {},
    }
    if ensayo:
        status = _safe_scenario_status(dict(ensayo))
        result["estado_ensayo"] = status
    else:
        result["estado_ensayo"] = resolve_cylinder_scenario({})
    if programa_rows and include_layers:
        result["capas"] = _combined_program_layers_with_actuals(conn, [dict(row) for row in programa_rows], colado_id)
        result["resumen"] = _schedule_summary(result["capas"])
    simple = _simple_evaluation_context(conn, colado_id, result)
    result["siguiente_zona_programa"] = simple["siguiente_zona_programa"]
    result["salida_planta_sugerida"] = simple["salida_planta_sugerida"]
    result["puede_evaluar"] = simple["puede_evaluar"]
    result["motivo_bloqueo"] = simple["motivo_bloqueo"]
    result["zona_evaluacion_cilindro"] = simple["zona_evaluacion_cilindro"]
    result["salida_planta_evaluacion"] = simple["salida_planta_evaluacion"]
    result["puede_evaluar_cilindro"] = simple["puede_evaluar_cilindro"]
    result["motivo_bloqueo_evaluacion"] = simple["motivo_bloqueo_evaluacion"]
    return result


def _revision_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    status = _safe_scenario_status(item)
    item["estado_ensayo"] = status["estado"]
    item["escenario_resuelto"] = status.get("escenario_activo")
    item["mensaje"] = status.get("mensaje")
    item["receta_sugerida"] = status.get("receta_sugerida")
    return item


def _safe_scenario_status(item: dict[str, Any]) -> dict[str, Any]:
    try:
        return resolve_cylinder_scenario(item)
    except ValueError as exc:
        return {
            "escenario_activo": None,
            "estado": "REQUIERE_CORRECCION",
            "alerta": "ENSAYO_INCONSISTENTE",
            "mensaje": str(exc),
            "receta_sugerida": None,
        }


def _combined_program_layers_with_actuals(
    conn: sqlite3.Connection,
    programs: list[dict[str, Any]],
    colado_id: int,
) -> list[dict[str, Any]]:
    if not programs:
        return []
    actual_by_zone = _actuals_by_zone(conn, colado_id)
    max_zone = max(
        [int(program.get("total_layers") or 0) for program in programs]
        + [int(zone) for zone in actual_by_zone.keys()]
    )
    min_zone = min(int(program.get("start_zone") or 1) for program in programs)
    layers: list[dict[str, Any]] = []
    for zone_number in range(min_zone, max_zone + 1):
        program = _program_for_zone(programs, zone_number)
        if not program:
            continue
        item = _layer_from_program(program, zone_number)
        actual = actual_by_zone.get(zone_number) or {}
        item["numero_olla"] = actual.get("numero_olla")
        item["hora_real_salida_planta"] = actual.get("hora_salida_planta")
        item["hora_real_llegada_obra"] = actual.get("hora_llegada_obra")
        item["hora_real_inicio_descarga"] = actual.get("hora_inicio_descarga")
        item["hora_real_fin_descarga"] = actual.get("hora_fin_descarga")
        item["desviacion_salida_min"] = _diff_minutes(item.get("hora_programada"), item.get("hora_real_salida_planta"))
        item["estado_programa"] = _layer_status(item)
        layers.append(item)
    return layers


def _actuals_by_zone(conn: sqlite3.Connection, colado_id: int) -> dict[int, dict[str, Any]]:
    return {
        int(row["zona_numero"]): dict(row)
        for row in conn.execute(
            """
            SELECT z.zona_numero, d.numero_olla,
                   COALESCE(d.hora_salida_planta, z.hora_salida_planta) AS hora_salida_planta,
                   d.hora_llegada_obra, d.hora_inicio_descarga, d.hora_fin_descarga,
                   z.origen_generacion, z.estado
            FROM zonas_colado z
            LEFT JOIN descargas_olla d ON d.id = z.descarga_olla_id
            WHERE z.colado_id = ?
            """,
            (colado_id,),
        ).fetchall()
    }


def _simple_evaluation_context(conn: sqlite3.Connection, colado_id: int, schedule: dict[str, Any]) -> dict[str, Any]:
    zones = _actuals_by_zone(conn, colado_id)
    inherited_zones = {
        number
        for number, zone in zones.items()
        if _is_inherited_actual(zone)
    }
    real_zones = {
        number: zone
        for number, zone in zones.items()
        if number not in inherited_zones
    }
    programmed_zones = {int(layer["zona_numero"]) for layer in schedule.get("capas") or []}
    pending_real = [
        int(layer["zona_numero"])
        for layer in schedule.get("capas") or []
        if int(layer["zona_numero"]) not in inherited_zones and not layer.get("hora_real_salida_planta")
    ]
    candidates = [zone for zone in sorted(real_zones) if zone not in programmed_zones]
    if pending_real:
        candidates.append(min(pending_real))
    if not candidates and real_zones:
        candidates.append(max(real_zones) + 1)
    if not candidates and inherited_zones:
        candidates.append(max(inherited_zones) + 1)
    zone_number = min(candidates) if candidates else 1
    actual = real_zones.get(zone_number) or {}
    salida = actual.get("hora_salida_planta")
    if not actual:
        reason = f"Registra la olla de la Zona {zone_number} antes de evaluar cilindro."
    elif not salida:
        reason = f"La Zona {zone_number} no tiene salida de planta registrada."
    else:
        reason = None
    evaluation = _cylinder_evaluation_zone(real_zones, inherited_zones, schedule, zone_number)
    return {
        "siguiente_zona_programa": zone_number,
        "salida_planta_sugerida": salida,
        "puede_evaluar": reason is None,
        "motivo_bloqueo": reason,
        **evaluation,
    }


def _cylinder_evaluation_zone(
    real_zones: dict[int, dict[str, Any]],
    inherited_zones: set[int],
    schedule: dict[str, Any],
    fallback_zone_number: int,
) -> dict[str, Any]:
    evaluated_zones = {
        int(item.get("start_zone") or 1)
        for item in schedule.get("historial") or []
        if item.get("start_zone") is not None
    }
    registered_real_zones = [
        number
        for number, zone in sorted(real_zones.items())
        if zone.get("hora_salida_planta")
    ]
    pending_evaluation = [number for number in registered_real_zones if number not in evaluated_zones]
    if pending_evaluation:
        zone_number = pending_evaluation[0]
    elif registered_real_zones:
        zone_number = registered_real_zones[-1]
    elif inherited_zones:
        zone_number = max(inherited_zones) + 1
    else:
        zone_number = fallback_zone_number

    actual = real_zones.get(zone_number) or {}
    salida = actual.get("hora_salida_planta")
    if not actual:
        reason = f"Registra la olla de la Zona {zone_number} con salida de planta antes de evaluar cilindro."
    elif not salida:
        reason = f"La Zona {zone_number} no tiene salida de planta registrada."
    else:
        reason = None
    return {
        "zona_evaluacion_cilindro": zone_number,
        "salida_planta_evaluacion": salida,
        "puede_evaluar_cilindro": reason is None,
        "motivo_bloqueo_evaluacion": reason,
    }


def _is_inherited_actual(zone: dict[str, Any]) -> bool:
    return (
        str(zone.get("origen_generacion") or "").lower() == "existente_previo"
        or str(zone.get("estado") or "").upper() == "EXISTENTE_PREVIO"
    )


def _program_for_zone(programs: list[dict[str, Any]], zone_number: int) -> dict[str, Any] | None:
    applicable = [
        program
        for program in programs
        if int(program.get("start_zone") or 1) <= zone_number <= int(program.get("total_layers") or 0)
    ]
    if not applicable:
        return None
    return sorted(applicable, key=lambda program: (int(program.get("start_zone") or 1), int(program.get("id") or 0)))[-1]


def _layer_from_program(program: dict[str, Any], zone_number: int) -> dict[str, Any]:
    start_zone = int(program.get("start_zone") or 1)
    offset = float(program.get("layer_interval_minutes") or 0.0) * (zone_number - start_zone)
    target = datetime.fromisoformat(str(program["t_fabricacion"]).replace(" ", "T"))
    target = target.replace(second=0, microsecond=0)
    return {
        "programa_id": program.get("id"),
        "revision_id": program.get("ensayo_cilindro_id"),
        "capa_numero": zone_number,
        "zona_numero": zone_number,
        "hora_programada": (target.replace(second=0, microsecond=0) + _minutes_delta(offset)).isoformat(timespec="minutes"),
        "offset_min": round(offset, 2),
        "estado": "PROGRAMADA",
        "escenario": program.get("escenario"),
        "step_cm": program.get("step_cm"),
        "step_minutes": program.get("step_minutes"),
        "speed_cm_h": program.get("speed_cm_h"),
        "origen_programa": f"Revision {program.get('ensayo_cilindro_id')} desde Zona {start_zone}",
    }


def _minutes_delta(minutes: float):
    from datetime import timedelta

    return timedelta(minutes=minutes)


def _layer_status(layer: dict[str, Any]) -> str:
    if not layer.get("hora_real_salida_planta"):
        return "PENDIENTE"
    drift = layer.get("desviacion_salida_min")
    if drift is None:
        return "SIN_COMPARACION"
    if abs(float(drift)) <= 10:
        return "EN_TIEMPO"
    return "ATRASADO" if float(drift) > 0 else "ADELANTADO"


def _schedule_summary(layers: list[dict[str, Any]]) -> dict[str, Any]:
    if not layers:
        return {"total_capas": 0, "capas_registradas": 0, "alertas": []}
    registered = [item for item in layers if item.get("hora_real_salida_planta")]
    alerts = [item for item in layers if item.get("estado_programa") in ("ATRASADO", "ADELANTADO")]
    next_layer = next((item for item in layers if not item.get("hora_real_salida_planta")), None)
    return {
        "total_capas": len(layers),
        "capas_registradas": len(registered),
        "siguiente_capa": next_layer,
        "alertas": alerts,
    }


def _required_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("La hora de fabricacion/salida de planta es requerida.")
    return _normalize_dt(text)


def _normalize_dt(value: Any) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).strip().replace(" ", "T")).isoformat(timespec="minutes")
    except ValueError as exc:
        raise ValueError("Fecha/hora invalida.") from exc


def _diff_minutes(expected: Any, actual: Any) -> float | None:
    if not expected or not actual:
        return None
    start = datetime.fromisoformat(str(expected).replace(" ", "T"))
    end = datetime.fromisoformat(str(actual).replace(" ", "T"))
    return round((end - start).total_seconds() / 60.0, 2)


__all__ = ["get_cylinder_test_schedule", "save_cylinder_test_schedule"]
