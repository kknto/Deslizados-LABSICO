"""Repository functions for mold physical configuration."""

from __future__ import annotations

import sqlite3
from typing import Any

from slipform.config import DEFAULT_ADVANCE_CM, DEFAULT_ADVANCE_INTERVAL_MIN, DEFAULT_ADVANCE_SPEED_CM_H
from slipform.repositories.schema import init_db


def get_mold_config(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM configuracion_molde ORDER BY id LIMIT 1").fetchone()
    if row is None:
        init_db(conn)
        row = conn.execute("SELECT * FROM configuracion_molde ORDER BY id LIMIT 1").fetchone()
    return dict(row)


def default_advance_recipe(conn: sqlite3.Connection, colado_id: int) -> dict[str, Any]:
    cfg = get_mold_config(conn)
    advance = float(cfg["avance_objetivo_cm_5min"] or DEFAULT_ADVANCE_CM)
    interval = DEFAULT_ADVANCE_INTERVAL_MIN
    speed = float(cfg["velocidad_objetivo_cm_h"] or DEFAULT_ADVANCE_SPEED_CM_H)
    return {
        "id": None,
        "colado_id": colado_id,
        "fecha_hora": None,
        "avance_objetivo_cm": advance,
        "intervalo_objetivo_min": interval,
        "velocidad_objetivo_cm_h": speed,
        "tolerancia_velocidad_min_cm_h": max(0.0, speed - 5.0),
        "tolerancia_velocidad_max_cm_h": speed + 5.0,
        "activo": 1,
        "motivo": "Default de configuracion del molde.",
        "operador": None,
        "supervisor": None,
    }


def upsert_mold_config(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    row = conn.execute(
        """
        INSERT INTO configuracion_molde(
            nombre, altura_molde_m, altura_zona_m, zonas_por_molde,
            velocidad_objetivo_cm_h, avance_objetivo_cm_5min,
            residencia_minima_h, residencia_preferente_h
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(nombre) DO UPDATE SET
            altura_molde_m = excluded.altura_molde_m,
            altura_zona_m = excluded.altura_zona_m,
            zonas_por_molde = excluded.zonas_por_molde,
            velocidad_objetivo_cm_h = excluded.velocidad_objetivo_cm_h,
            avance_objetivo_cm_5min = excluded.avance_objetivo_cm_5min,
            residencia_minima_h = excluded.residencia_minima_h,
            residencia_preferente_h = excluded.residencia_preferente_h
        RETURNING id
        """,
        (
            payload.get("nombre") or "Default 1.20m",
            float(payload.get("altura_molde_m") or 1.20),
            float(payload.get("altura_zona_m") or 0.30),
            int(payload.get("zonas_por_molde") or 4),
            float(payload.get("velocidad_objetivo_cm_h") or DEFAULT_ADVANCE_SPEED_CM_H),
            float(payload.get("avance_objetivo_cm_5min") or DEFAULT_ADVANCE_CM),
            float(payload.get("residencia_minima_h") or 4.0),
            float(payload.get("residencia_preferente_h") or 4.5),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


__all__ = ["default_advance_recipe", "get_mold_config", "upsert_mold_config"]
