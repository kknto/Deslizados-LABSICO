"""Repository functions for slipform concrete zones."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from slipform.domain.validation import (
    optional_float,
    normalize_datetime,
    parse_datetime,
    validate_measurements,
    validate_origin,
)
from slipform.repositories.colados_repo import get_colado
from slipform.repositories.descargas_repo import create_descarga, update_descarga
from slipform.repositories.mold_config_repo import get_mold_config
from slipform.repositories.audit_repo import insert_audit
from slipform.repositories.scada_repo import insert_field_release


def create_zone(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    colado = get_colado(conn, int(payload["colado_id"]))
    if not colado:
        raise ValueError("Colado no encontrado.")
    cfg = get_mold_config(conn)
    zone_number = int(payload.get("zona_numero") or _next_zone_number(conn, int(payload["colado_id"])))
    height_cm = float(payload.get("altura_zona_cm") or float(cfg["altura_zona_m"]) * 100.0)
    lower = optional_float(payload.get("elevacion_inferior_cm"))
    if lower is None:
        lower = (zone_number - 1) * height_cm
    upper = optional_float(payload.get("elevacion_superior_cm"))
    if upper is None:
        upper = lower + height_cm
    plant_departure_raw = payload.get("hora_salida_planta") or payload.get("hora_referencia_madurez") or payload.get("hora_inicio_llenado")
    plant_departure = normalize_datetime(plant_departure_raw, timespec="minutes")
    start = normalize_datetime(payload.get("hora_inicio_llenado") or plant_departure, timespec="minutes")
    finish = payload.get("hora_fin_llenado")
    finish = normalize_datetime(finish, timespec="minutes") if finish else None
    reference_raw = payload.get("hora_referencia_madurez") or plant_departure
    reference = normalize_datetime(reference_raw, timespec="minutes")
    volume_m3 = optional_float(payload.get("volumen_m3"))
    if volume_m3 is None:
        volume_m3 = optional_float(payload.get("volumen_por_olla_m3"))
    if volume_m3 is None:
        volume_m3 = 5.0
    row = conn.execute(
        """
        INSERT INTO zonas_colado(
            colado_id, descarga_olla_id, zona_numero, elevacion_inferior_cm,
            elevacion_superior_cm, volumen_m3, hora_salida_planta, hora_inicio_llenado, hora_fin_llenado,
            hora_referencia_madurez, mezcla_id, curva_id, temperatura_inicial_c,
            origen_generacion, avance_generador_id, estado
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(payload["colado_id"]),
            _optional_int(payload.get("descarga_olla_id")),
            zone_number,
            lower,
            upper,
            volume_m3,
            plant_departure,
            start,
            finish,
            reference,
            _optional_int(payload.get("mezcla_id")) or colado.get("mezcla_id"),
            _optional_int(payload.get("curva_id")) or colado.get("curva_id"),
            optional_float(payload.get("temperatura_inicial_c")),
            payload.get("origen_generacion") or "manual",
            _optional_int(payload.get("avance_generador_id")),
            payload.get("estado") or "EN_RESIDENCIA",
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def register_truck_zone(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    colado_id = int(payload["colado_id"])
    colado = get_colado(conn, colado_id)
    if not colado:
        raise ValueError("Colado no encontrado.")
    if not payload.get("hora_salida_planta"):
        raise ValueError("La olla requiere hora de salida de planta.")

    zone_number = _truck_number(payload.get("zona_numero") or payload.get("numero_olla"))
    load_number = str(payload.get("numero_olla") or zone_number)
    cfg = get_mold_config(conn)
    height_cm = float(payload.get("altura_zona_cm") or float(cfg["altura_zona_m"]) * 100.0)
    lower = (zone_number - 1) * height_cm
    upper = zone_number * height_cm
    plant_departure = normalize_datetime(payload["hora_salida_planta"], timespec="minutes")
    volume_m3 = optional_float(payload.get("volumen_m3")) or optional_float(payload.get("volumen_por_olla_m3")) or 5.0
    curve_id = _optional_int(payload.get("curva_id")) or colado.get("curva_id")
    initial_temp = (
        optional_float(payload.get("temperatura_inicial_c"))
        or optional_float(payload.get("temperatura_llegada_c"))
        or optional_float(payload.get("temperatura_salida_c"))
    )
    if curve_id in (None, "") and initial_temp is None:
        raise ValueError("Captura temperatura de llegada de la olla o selecciona una curva de referencia para calcular madurez.")
    load_payload = {
        **payload,
        "colado_id": colado_id,
        "numero_olla": load_number,
        "volumen_m3": volume_m3,
        "hora_salida_planta": plant_departure,
        "origen_generacion": payload.get("origen_generacion") or "registrar_olla",
        "estado_operativo": payload.get("estado_operativo") or "CONFIRMADA_EN_MOLDE",
    }
    existing_zone = conn.execute(
        """
        SELECT *
        FROM zonas_colado
        WHERE colado_id = ? AND zona_numero = ?
        ORDER BY id
        LIMIT 1
        """,
        (colado_id, zone_number),
    ).fetchone()
    if (
        existing_zone
        and str(existing_zone["origen_generacion"] or "").lower() == "existente_previo"
        and not bool(payload.get("reemplazar_zona_heredada"))
    ):
        raise ValueError("La zona ya existe como previa; confirma que deseas reemplazarla con una olla de este colado.")
    existing_load = conn.execute(
        """
        SELECT *
        FROM descargas_olla
        WHERE colado_id = ? AND CAST(numero_olla AS TEXT) = ?
        ORDER BY id
        LIMIT 1
        """,
        (colado_id, load_number),
    ).fetchone()
    if existing_load:
        descarga_id = int(existing_load["id"])
        descarga = update_descarga(conn, descarga_id, load_payload)
        created_load = False
    else:
        descarga_id = create_descarga(conn, load_payload)
        descarga = dict(conn.execute("SELECT * FROM descargas_olla WHERE id = ?", (descarga_id,)).fetchone())
        created_load = True

    start = normalize_datetime(payload.get("hora_inicio_descarga") or plant_departure, timespec="minutes")
    finish = payload.get("hora_fin_descarga")
    finish = normalize_datetime(finish, timespec="minutes") if finish else None
    if existing_zone:
        zone_id = int(existing_zone["id"])
        conn.execute(
            """
            UPDATE zonas_colado
            SET descarga_olla_id = ?,
                elevacion_inferior_cm = ?,
                elevacion_superior_cm = ?,
                volumen_m3 = ?,
                hora_salida_planta = ?,
                hora_inicio_llenado = ?,
                hora_fin_llenado = ?,
                hora_referencia_madurez = ?,
                mezcla_id = ?,
                curva_id = ?,
                temperatura_inicial_c = COALESCE(?, temperatura_inicial_c),
                origen_generacion = ?,
                estado = ?
            WHERE id = ?
            """,
            (
                descarga_id,
                lower,
                upper,
                volume_m3,
                plant_departure,
                start,
                finish,
                plant_departure,
                _optional_int(payload.get("mezcla_id")) or colado.get("mezcla_id"),
                curve_id,
                initial_temp,
                payload.get("origen_generacion") or "registrar_olla",
                payload.get("estado") or "CONFIRMADA_EN_MOLDE",
                zone_id,
            ),
        )
        conn.commit()
        created_zone = False
    else:
        zone_id = create_zone(
            conn,
            {
                "colado_id": colado_id,
                "descarga_olla_id": descarga_id,
                "zona_numero": zone_number,
                "elevacion_inferior_cm": lower,
                "elevacion_superior_cm": upper,
                "volumen_m3": volume_m3,
                "hora_salida_planta": plant_departure,
                "hora_inicio_llenado": start,
                "hora_fin_llenado": finish,
                "hora_referencia_madurez": plant_departure,
                "mezcla_id": payload.get("mezcla_id") or colado.get("mezcla_id"),
                "curva_id": curve_id,
                "temperatura_inicial_c": initial_temp,
                "origen_generacion": payload.get("origen_generacion") or "registrar_olla",
                "estado": payload.get("estado") or "CONFIRMADA_EN_MOLDE",
            },
        )
        created_zone = True

    return {
        "descarga": descarga,
        "zona": get_zone(conn, zone_id),
        "descarga_creada": created_load,
        "zona_creada": created_zone,
    }


def initialize_colado_start_offset(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    colado_id = int(payload["colado_id"])
    colado = get_colado(conn, colado_id)
    if not colado:
        raise ValueError("Colado no encontrado.")
    first_new_zone = int(payload.get("primera_zona_nueva") or 1)
    if first_new_zone < 1:
        raise ValueError("La primera zona nueva debe ser mayor o igual a 1.")
    cfg = get_mold_config(conn)
    required_zones = int(cfg["zonas_por_molde"])
    start_time = normalize_datetime(
        payload.get("hora_inicio_operativo") or datetime.now().isoformat(timespec="seconds"),
        timespec="minutes",
    )
    motivo = str(payload.get("motivo") or "Arranque con zona previa existente").strip()
    supervisor = str(payload.get("supervisor") or "").strip()
    if first_new_zone > 1 and not supervisor:
        raise ValueError("El arranque con zona previa requiere supervisor.")
    operator = payload.get("operador")
    inherited_ids: list[int] = []
    inherited_zones: list[dict[str, Any]] = []
    height_cm = float(cfg["altura_zona_m"]) * 100.0
    base_initial_cm = max(0.0, (first_new_zone - required_zones) * height_cm)
    crown_initial_cm = base_initial_cm + required_zones * height_cm
    first_inherited_zone = max(1, first_new_zone - required_zones + 1)
    inherited_numbers = list(range(first_inherited_zone, first_new_zone))
    if base_initial_cm > 0:
        _insert_initial_mold_position(conn, colado_id, base_initial_cm, start_time, first_new_zone, operator)
    for zone_number in inherited_numbers:
        existing_zone = conn.execute(
            """
            SELECT id
            FROM zonas_colado
            WHERE colado_id = ? AND zona_numero = ?
            ORDER BY id
            LIMIT 1
            """,
            (colado_id, zone_number),
        ).fetchone()
        if existing_zone:
            zone_id = int(existing_zone["id"])
            conn.execute(
                """
                UPDATE zonas_colado
                SET origen_generacion = 'existente_previo',
                    estado = 'EXISTENTE_PREVIO',
                    hora_referencia_madurez = COALESCE(hora_referencia_madurez, ?),
                    hora_salida_planta = NULL,
                    descarga_olla_id = NULL
                WHERE id = ?
                """,
                (start_time, zone_id),
            )
        else:
            zone_id = create_zone(
                conn,
                {
                    "colado_id": colado_id,
                    "zona_numero": zone_number,
                    "elevacion_inferior_cm": (zone_number - 1) * height_cm,
                    "elevacion_superior_cm": zone_number * height_cm,
                    "volumen_m3": 0,
                    "hora_inicio_llenado": start_time,
                    "hora_referencia_madurez": start_time,
                    "mezcla_id": colado.get("mezcla_id"),
                    "curva_id": colado.get("curva_id"),
                    "temperatura_inicial_c": payload.get("temperatura_concreto_c") or 23,
                    "origen_generacion": "existente_previo",
                    "estado": "EXISTENTE_PREVIO",
                },
            )
            conn.execute(
                """
                UPDATE zonas_colado
                SET hora_salida_planta = NULL
                WHERE id = ?
                """,
                (zone_id,),
            )
        release_payload = {
            "colado_id": colado_id,
            "zona_colado_id": zone_id,
            "fecha_hora": start_time,
            "madurez_calculada_pct": 0.0,
            "madurez_operativa_pct": 90.0,
            "temperatura_concreto_c": optional_float(payload.get("temperatura_concreto_c")) or 23.0,
            "temperatura_ambiente_c": payload.get("temperatura_ambiente_c"),
            "humedad_relativa_pct": payload.get("humedad_relativa_pct"),
            "condicion_observada": payload.get("condicion_observada") or "existente_previo",
            "checklist": {
                "no_desmorona": True,
                "no_se_pega": True,
                "acabado_aceptable": True,
                "sin_arrastre": True,
            },
            "motivo": motivo,
            "operador": operator,
            "supervisor": supervisor or "Campo",
        }
        insert_field_release(conn, release_payload)
        inherited_ids.append(zone_id)
        inherited_zones.append(get_zone(conn, zone_id))
    insert_audit(
        conn,
        "INITIALIZE_START_OFFSET",
        "colados",
        entity_id=colado_id,
        colado_id=colado_id,
        operator=operator,
        reason=motivo,
        detail={
            "primera_zona_nueva": first_new_zone,
            "zonas_previas": [zone["zona_numero"] for zone in inherited_zones],
            "hora_inicio_operativo": start_time,
            "base_inicial_cm": base_initial_cm,
            "corona_inicial_cm": crown_initial_cm,
        },
    )
    conn.commit()
    return {
        "zonas_heredadas": inherited_zones,
        "ids": inherited_ids,
        "primera_zona_nueva": first_new_zone,
        "siguiente_olla_sugerida": first_new_zone,
        "zonas_previas_existentes": max(0, first_new_zone - 1),
        "zonas_previas_numeros": inherited_numbers,
        "base_inicial_cm": round(base_initial_cm, 3),
        "corona_inicial_cm": round(crown_initial_cm, 3),
        "ventana_inicial_molde": {
            "base_cm": round(base_initial_cm, 3),
            "corona_cm": round(crown_initial_cm, 3),
            "altura_molde_cm": round(required_zones * height_cm, 3),
        },
    }


def _insert_initial_mold_position(
    conn: sqlite3.Connection,
    colado_id: int,
    base_initial_cm: float,
    start_time: str,
    first_new_zone: int,
    operator: str | None,
) -> None:
    existing = conn.execute(
        """
        SELECT id, avance_acumulado_cm, origen
        FROM avances_molde
        WHERE colado_id = ?
        ORDER BY id
        LIMIT 1
        """,
        (colado_id,),
    ).fetchone()
    if existing:
        return
    conn.execute(
        """
        INSERT INTO avances_molde(
            colado_id, receta_avance_id, fecha_hora, minuto_transcurrido, avance_cm,
            avance_acumulado_cm, velocidad_real_cm_h, intervalo_minutos,
            origen, observacion, operador
        )
        VALUES (?, NULL, ?, 0, 0, ?, 0, 0, 'arranque_inicial', ?, ?)
        """,
        (
            colado_id,
            start_time,
            round(base_initial_cm, 3),
            f"Arranque operativo en Zona {first_new_zone}.",
            operator,
        ),
    )


def generate_zones(conn: sqlite3.Connection, payload: dict[str, Any]) -> list[int]:
    colado = get_colado(conn, int(payload["colado_id"]))
    if not colado:
        raise ValueError("Colado no encontrado.")
    cfg = get_mold_config(conn)
    start = parse_datetime(str(payload.get("hora_salida_planta_olla_1") or payload["hora_zona_1"]))
    interval = float(payload.get("intervalo_minutos") or 60)
    start_zone = int(payload.get("zona_inicial") or payload.get("start_zone") or payload.get("primera_zona_nueva") or 1)
    if start_zone < 1:
        raise ValueError("La zona inicial debe ser mayor o igual a 1.")
    count = int(payload.get("zonas") or cfg["zonas_por_molde"])
    height_cm = float(payload.get("altura_zona_cm") or float(cfg["altura_zona_m"]) * 100.0)
    volume_m3 = optional_float(payload.get("volumen_por_olla_m3")) or optional_float(payload.get("volumen_m3")) or 5.0
    ids: list[int] = []
    for index in range(count):
        zone_number = start_zone + index
        plant_dt = start + timedelta(minutes=index * interval)
        descarga_id = payload.get("descarga_olla_id")
        if not descarga_id:
            descarga_id = create_descarga(
                conn,
                {
                    "colado_id": colado["id"],
                    "numero_olla": zone_number,
                    "volumen_m3": volume_m3,
                    "hora_salida_planta": plant_dt.isoformat(timespec="minutes"),
                    "hora_inicio_descarga": payload.get("hora_inicio_descarga"),
                    "temperatura_salida_c": payload.get("temperatura_salida_c"),
                    "temperatura_llegada_c": payload.get("temperatura_llegada_c"),
                    "revenimiento_cm": payload.get("revenimiento_cm"),
                    "origen_generacion": "generador_zonas",
                },
            )
        ids.append(
            create_zone(
                conn,
                {
                    "colado_id": colado["id"],
                    "descarga_olla_id": descarga_id,
                    "zona_numero": zone_number,
                    "elevacion_inferior_cm": (zone_number - 1) * height_cm,
                    "elevacion_superior_cm": zone_number * height_cm,
                    "volumen_m3": volume_m3,
                    "hora_salida_planta": plant_dt.isoformat(timespec="minutes"),
                    "hora_inicio_llenado": plant_dt.isoformat(timespec="minutes"),
                    "hora_fin_llenado": plant_dt.isoformat(timespec="minutes"),
                    "hora_referencia_madurez": plant_dt.isoformat(timespec="minutes"),
                    "mezcla_id": payload.get("mezcla_id") or colado.get("mezcla_id"),
                    "curva_id": payload.get("curva_id") or colado.get("curva_id"),
                    "temperatura_inicial_c": payload.get("temperatura_inicial_c"),
                },
            )
        )
    return ids


def generate_initial_zones(conn: sqlite3.Connection, payload: dict[str, Any]) -> list[int]:
    return generate_zones(conn, payload)


def insert_zone_reading(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    _validate_zone_reading_payload(conn, payload)
    zone = get_zone(conn, int(payload["zona_colado_id"]))
    if not zone:
        raise ValueError("Zona no encontrada.")
    fecha_hora = normalize_datetime(payload.get("fecha_hora") or datetime.now().isoformat(timespec="seconds"))
    minute = payload.get("minuto_desde_zona")
    if minute in (None, ""):
        minute = (parse_datetime(fecha_hora) - parse_datetime(str(zone["hora_referencia_madurez"]))).total_seconds() / 60.0
    row = conn.execute(
        """
        INSERT INTO lecturas_zona(
            zona_colado_id, sensor_id, fecha_hora, minuto_desde_zona,
            temperatura_concreto_c, temperatura_ambiente_c, humedad_relativa_pct,
            origen, valido
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(payload["zona_colado_id"]),
            _optional_int(payload.get("sensor_id")),
            fecha_hora,
            round(float(minute), 3),
            optional_float(payload.get("temperatura_concreto_c")),
            optional_float(payload.get("temperatura_ambiente_c")),
            optional_float(payload.get("humedad_relativa_pct")),
            payload.get("origen") or "manual",
            int(payload.get("valido", 1)),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def ensure_continuous_zones(
    conn: sqlite3.Connection,
    colado_id: int,
    avance_anterior_cm: float,
    avance_actual_cm: float,
    fecha_hora_avance: str,
    previous_fecha_hora: str | None = None,
    advance_id: int | None = None,
) -> list[int]:
    from slipform.repositories.avances_repo import get_active_advance_recipe

    colado = get_colado(conn, colado_id)
    if not colado:
        raise ValueError("Colado no encontrado.")
    cfg = get_mold_config(conn)
    recipe = get_active_advance_recipe(conn, colado_id)
    zones = get_zones(conn, colado_id)
    if len(zones) < int(cfg["zonas_por_molde"]):
        return []

    height_cm = float(cfg["altura_zona_m"]) * 100.0
    mold_height_cm = float(cfg["altura_molde_m"]) * 100.0
    target_speed_cm_min = float(recipe["velocidad_objetivo_cm_h"] or cfg["velocidad_objetivo_cm_h"]) / 60.0
    current_top = float(avance_actual_cm) + mold_height_cm
    max_upper = max(float(zone["elevacion_superior_cm"]) for zone in zones)
    created_ids: list[int] = []

    while max_upper < current_top - 0.0001:
        lower = max_upper
        upper = lower + height_cm
        start_dt = _estimate_top_crossing_time(
            lower,
            float(avance_anterior_cm) + mold_height_cm,
            current_top,
            fecha_hora_avance,
            previous_fecha_hora,
            target_speed_cm_min,
        )
        fill_minutes = height_cm / target_speed_cm_min if target_speed_cm_min > 0 else 60.0
        zone_number = _next_zone_number(conn, colado_id)
        plant_dt = _estimate_next_truck_departure(conn, colado_id, interval_minutes=60.0)
        descarga_id = create_descarga(
            conn,
            {
                "colado_id": colado_id,
                "numero_olla": zone_number,
                "volumen_m3": 5.0,
                "hora_salida_planta": plant_dt.isoformat(timespec="minutes"),
                "hora_inicio_descarga": start_dt.isoformat(timespec="minutes"),
                "origen_generacion": "automatico_avance",
            },
        )
        zone_id = create_zone(
            conn,
            {
                "colado_id": colado_id,
                "descarga_olla_id": descarga_id,
                "zona_numero": zone_number,
                "elevacion_inferior_cm": lower,
                "elevacion_superior_cm": upper,
                "volumen_m3": 5.0,
                "hora_salida_planta": plant_dt.isoformat(timespec="minutes"),
                "hora_inicio_llenado": start_dt.isoformat(timespec="minutes"),
                "hora_fin_llenado": (start_dt + timedelta(minutes=fill_minutes)).isoformat(timespec="minutes"),
                "hora_referencia_madurez": plant_dt.isoformat(timespec="minutes"),
                "mezcla_id": colado.get("mezcla_id"),
                "curva_id": colado.get("curva_id"),
                "origen_generacion": "automatico_avance",
                "avance_generador_id": advance_id,
                "estado": "ZONA_EN_LLENADO",
            },
        )
        created_ids.append(zone_id)
        max_upper = upper
    return created_ids


def get_zones_generated_by_advance(conn: sqlite3.Connection, advance_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM zonas_colado
            WHERE avance_generador_id = ?
            ORDER BY elevacion_inferior_cm, id
            """,
            (advance_id,),
        ).fetchall()
    ]


def get_zones(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT z.*,
               d.numero_olla,
               COALESCE(d.volumen_m3, z.volumen_m3) AS volumen_olla_m3,
               COALESCE(d.hora_salida_planta, z.hora_salida_planta, z.hora_referencia_madurez) AS hora_salida_planta,
               d.hora_llegada_obra,
               d.hora_inicio_descarga,
               d.hora_fin_descarga,
               d.temperatura_salida_c,
               d.temperatura_llegada_c,
               d.revenimiento_cm,
               d.origen_generacion AS origen_olla,
               COALESCE(d.estado_operativo, z.estado) AS estado_olla,
               m.nombre AS mezcla_nombre,
               cl.nombre_curva
        FROM zonas_colado z
        LEFT JOIN descargas_olla d ON d.id = z.descarga_olla_id
        LEFT JOIN mezclas m ON m.id = z.mezcla_id
        LEFT JOIN curvas_laboratorio cl ON cl.id = z.curva_id
        WHERE z.colado_id = ?
        ORDER BY z.elevacion_inferior_cm, z.id
        """,
        (colado_id,),
    ).fetchall()
    return [_normalize_inherited_zone(dict(row)) for row in rows]


def list_zones(conn: sqlite3.Connection, colado_id: int) -> list[dict[str, Any]]:
    return get_zones(conn, colado_id)


def get_zone(conn: sqlite3.Connection, zone_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT z.*,
               d.numero_olla,
               COALESCE(d.volumen_m3, z.volumen_m3) AS volumen_olla_m3,
               COALESCE(d.hora_salida_planta, z.hora_salida_planta, z.hora_referencia_madurez) AS hora_salida_planta,
               d.hora_llegada_obra,
               d.hora_inicio_descarga,
               d.hora_fin_descarga,
               d.temperatura_salida_c,
               d.temperatura_llegada_c,
               d.revenimiento_cm,
               d.origen_generacion AS origen_olla,
               COALESCE(d.estado_operativo, z.estado) AS estado_olla
        FROM zonas_colado z
        LEFT JOIN descargas_olla d ON d.id = z.descarga_olla_id
        WHERE z.id = ?
        """,
        (zone_id,),
    ).fetchone()
    return _normalize_inherited_zone(dict(row)) if row else None


def _normalize_inherited_zone(zone: dict[str, Any]) -> dict[str, Any]:
    inherited = str(zone.get("origen_generacion") or "").lower() == "existente_previo"
    zone["es_zona_heredada"] = inherited
    if inherited:
        zone["numero_olla"] = None
        zone["volumen_olla_m3"] = 0.0
        zone["hora_salida_planta"] = None
        zone["origen_olla"] = "existente_previo"
        zone["estado_olla"] = "EXISTENTE_PREVIO"
    return zone


def get_zona(conn: sqlite3.Connection, zone_id: int) -> dict[str, Any] | None:
    return get_zone(conn, zone_id)


def get_zone_readings(conn: sqlite3.Connection, zone_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM lecturas_zona
            WHERE zona_colado_id = ? AND valido = 1
            ORDER BY minuto_desde_zona, id
            """,
            (zone_id,),
        ).fetchall()
    ]


def list_zone_readings(conn: sqlite3.Connection, zone_id: int) -> list[dict[str, Any]]:
    return get_zone_readings(conn, zone_id)


def invalidate_zone_reading(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    reading_id = int(payload["lectura_id"])
    reason = str(payload.get("motivo") or "").strip()
    if not reason:
        raise ValueError("Captura el motivo para anular la lectura.")
    row = conn.execute(
        """
        SELECT lz.*, z.colado_id, z.zona_numero
        FROM lecturas_zona lz
        JOIN zonas_colado z ON z.id = lz.zona_colado_id
        WHERE lz.id = ?
        """,
        (reading_id,),
    ).fetchone()
    if not row:
        raise ValueError("Lectura de zona no encontrada.")
    reading = dict(row)
    if payload.get("colado_id") not in (None, "") and int(payload["colado_id"]) != int(reading["colado_id"]):
        raise ValueError("La lectura no pertenece al colado activo.")
    if int(reading.get("valido") or 0) == 0:
        raise ValueError("La lectura ya estaba anulada.")
    conn.execute("UPDATE lecturas_zona SET valido = 0 WHERE id = ?", (reading_id,))
    insert_audit(
        conn,
        "INVALIDATE_ZONE_READING",
        "lecturas_zona",
        entity_id=reading_id,
        colado_id=int(reading["colado_id"]),
        operator=payload.get("operador"),
        reason=reason,
        detail={
            "zona_colado_id": reading.get("zona_colado_id"),
            "zona_numero": reading.get("zona_numero"),
            "fecha_hora": reading.get("fecha_hora"),
            "minuto_desde_zona": reading.get("minuto_desde_zona"),
            "temperatura_concreto_c": reading.get("temperatura_concreto_c"),
            "temperatura_ambiente_c": reading.get("temperatura_ambiente_c"),
            "humedad_relativa_pct": reading.get("humedad_relativa_pct"),
            "origen": reading.get("origen"),
        },
    )
    conn.commit()
    reading["valido"] = 0
    return reading


def upsert_zone(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    return create_zone(conn, payload)


def _validate_zone_reading_payload(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    zone = get_zone(conn, int(payload["zona_colado_id"]))
    if not zone:
        raise ValueError("Zona no encontrada.")
    if payload.get("colado_id") not in (None, "") and int(zone["colado_id"]) != int(payload["colado_id"]):
        raise ValueError("La zona no pertenece al colado activo.")
    validate_origin(payload.get("origen") or "manual")
    validate_measurements(payload)
    minute = payload.get("minuto_desde_zona")
    if minute not in (None, "") and float(minute) < 0:
        raise ValueError("El minuto desde zona no puede ser negativo.")


def _next_zone_number(conn: sqlite3.Connection, colado_id: int) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(MAX(zona_numero), 0) + 1 AS next
        FROM zonas_colado
        WHERE colado_id = ?
        """,
        (colado_id,),
    ).fetchone()
    return int(row["next"])


def _estimate_top_crossing_time(
    target_elevation_cm: float,
    previous_top_cm: float,
    current_top_cm: float,
    current_fecha_hora: str,
    previous_fecha_hora: str | None,
    target_speed_cm_min: float,
) -> datetime:
    current_dt = parse_datetime(current_fecha_hora)
    if previous_fecha_hora:
        previous_dt = parse_datetime(previous_fecha_hora)
    else:
        moved_cm = max(0.0, current_top_cm - previous_top_cm)
        minutes_back = moved_cm / target_speed_cm_min if target_speed_cm_min > 0 else 0.0
        previous_dt = current_dt - timedelta(minutes=minutes_back)

    total_cm = current_top_cm - previous_top_cm
    if total_cm <= 0:
        return current_dt
    fraction = (target_elevation_cm - previous_top_cm) / total_cm
    fraction = min(1.0, max(0.0, fraction))
    elapsed = current_dt - previous_dt
    return previous_dt + timedelta(seconds=elapsed.total_seconds() * fraction)


def _estimate_next_truck_departure(conn: sqlite3.Connection, colado_id: int, interval_minutes: float) -> datetime:
    rows = conn.execute(
        """
        SELECT hora_salida_planta
        FROM descargas_olla
        WHERE colado_id = ? AND hora_salida_planta IS NOT NULL AND hora_salida_planta <> ''
        ORDER BY id DESC
        LIMIT 2
        """,
        (colado_id,),
    ).fetchall()
    if rows:
        last = parse_datetime(str(rows[0]["hora_salida_planta"]))
        if len(rows) >= 2:
            previous = parse_datetime(str(rows[1]["hora_salida_planta"]))
            inferred = (last - previous).total_seconds() / 60.0
            if inferred > 0:
                interval_minutes = inferred
        return last + timedelta(minutes=interval_minutes or 60)
    zone = conn.execute(
        """
        SELECT hora_referencia_madurez
        FROM zonas_colado
        WHERE colado_id = ?
        ORDER BY zona_numero DESC, id DESC
        LIMIT 1
        """,
        (colado_id,),
    ).fetchone()
    if zone and zone["hora_referencia_madurez"]:
        return parse_datetime(str(zone["hora_referencia_madurez"])) + timedelta(minutes=interval_minutes or 60)
    return datetime.now()


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _truck_number(value: Any) -> int:
    if value in (None, ""):
        raise ValueError("La olla requiere numero.")
    text = str(value).strip()
    if text.lower().startswith("olla"):
        text = text.split()[-1]
    number = int(text)
    if number <= 0:
        raise ValueError("El numero de olla debe ser mayor a 0.")
    return number


def _optional_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


__all__ = [
    "create_zone",
    "ensure_continuous_zones",
    "generate_initial_zones",
    "generate_zones",
    "get_zone",
    "get_zone_readings",
    "get_zona",
    "get_zones",
    "get_zones_generated_by_advance",
    "initialize_colado_start_offset",
    "invalidate_zone_reading",
    "insert_zone_reading",
    "list_zone_readings",
    "list_zones",
    "register_truck_zone",
    "upsert_zone",
]
