"""Repository functions for mixes, lab curves and bootstrap data."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from slipform.config import DEFAULT_PARAMS
from slipform.repositories.colados_repo import list_colados
from slipform.repositories.project_repo import get_active_project


def upsert_mezcla(
    conn: sqlite3.Connection,
    nombre: str,
    dosificacion_hrp_cc: float | None = None,
    aditivo: str | None = "HRP",
) -> int:
    row = conn.execute(
        """
        SELECT id FROM mezclas
        WHERE nombre = ?
          AND (
              (dosificacion_hrp_cc IS NULL AND ? IS NULL)
              OR dosificacion_hrp_cc = ?
          )
        """,
        (nombre, dosificacion_hrp_cc, dosificacion_hrp_cc),
    ).fetchone()
    if row:
        return int(row["id"])

    row = conn.execute(
        """
        INSERT INTO mezclas(nombre, aditivo, dosificacion_hrp_cc, observaciones)
        VALUES (?, ?, ?, ?)
        RETURNING id
        """,
        (nombre, aditivo, dosificacion_hrp_cc, "Importada desde curvas de laboratorio."),
    ).fetchone()
    return int(row["id"])


def insert_curve(
    conn: sqlite3.Connection,
    mezcla_id: int,
    origen_archivo: str,
    nombre_curva: str,
    points: list[dict[str, float]],
    params: dict[str, float] | None = None,
) -> int:
    cfg = DEFAULT_PARAMS | (params or {})
    row = conn.execute(
        """
        SELECT id
        FROM curvas_laboratorio
        WHERE origen_archivo = ? AND nombre_curva = ?
        """,
        (origen_archivo, nombre_curva),
    ).fetchone()
    if row is None:
        row = conn.execute(
            """
            INSERT INTO curvas_laboratorio(
                mezcla_id, origen_archivo, nombre_curva, fecha_ensayo,
                madurez_objetivo_h_eq, parametros_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                mezcla_id,
                origen_archivo,
                nombre_curva,
                None,
                cfg["target_maturity_h_eq"],
                json.dumps(cfg, ensure_ascii=False),
            ),
        ).fetchone()
    curve_id = int(row["id"])
    conn.execute("DELETE FROM curvas_laboratorio_puntos WHERE curva_id = ?", (curve_id,))
    conn.executemany(
        """
        INSERT INTO curvas_laboratorio_puntos(
            curva_id, minuto, temperatura_concreto_c, madurez_arrhenius_h_eq
        )
        VALUES (?, ?, ?, ?)
        """,
        [
            (
                curve_id,
                point["minuto"],
                point["temperatura_concreto_c"],
                point["madurez_arrhenius_h_eq"],
            )
            for point in points
        ],
    )
    conn.commit()
    return curve_id


def get_reference_points(conn: sqlite3.Connection, curve_id: int | None) -> list[dict[str, Any]]:
    if curve_id is None:
        return []
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT minuto, temperatura_concreto_c, madurez_arrhenius_h_eq
            FROM curvas_laboratorio_puntos
            WHERE curva_id = ?
            ORDER BY minuto
            """,
            (curve_id,),
        ).fetchall()
    ]


def list_sensor_status(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                COALESCE(l.sensor_id, 0) AS sensor_id,
                CASE WHEN l.sensor_id IS NULL THEN 'sin_id' ELSE CAST(l.sensor_id AS TEXT) END AS sensor,
                MAX(l.fecha_hora) AS ultima_fecha_hora,
                l.colado_id,
                l.temperatura_concreto_c,
                l.temperatura_ambiente_c,
                l.humedad_relativa_pct,
                l.origen
            FROM lecturas l
            WHERE l.origen = 'sensor'
            GROUP BY COALESCE(l.sensor_id, 0)
            ORDER BY sensor_id
            """
        ).fetchall()
    ]


def list_bootstrap(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "params": DEFAULT_PARAMS,
        "proyecto": get_active_project(conn),
        "mezclas": [dict(row) for row in conn.execute("SELECT * FROM mezclas ORDER BY nombre").fetchall()],
        "curvas": [
            dict(row)
            for row in conn.execute(
                """
                SELECT cl.*, m.nombre AS mezcla_nombre
                FROM curvas_laboratorio cl
                JOIN mezclas m ON m.id = cl.mezcla_id
                ORDER BY cl.nombre_curva
                """
            ).fetchall()
        ],
        "colados": list_colados(conn),
        "sensores": list_sensor_status(conn),
    }


__all__ = ["get_reference_points", "insert_curve", "list_bootstrap", "list_sensor_status", "upsert_mezcla"]
