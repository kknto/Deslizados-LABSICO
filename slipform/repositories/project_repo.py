"""Repository functions for project metadata."""

from __future__ import annotations

import sqlite3
from typing import Any

from slipform.domain.validation import optional_float
from slipform.repositories.schema import init_db


def get_active_project(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM proyectos WHERE activo = 1 ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        init_db(conn)
        row = conn.execute("SELECT * FROM proyectos WHERE activo = 1 ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row)


def upsert_project(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    name = payload.get("nombre") or "Seybaplaya"
    if payload.get("activo", 1):
        conn.execute("UPDATE proyectos SET activo = 0")
    row = conn.execute(
        """
        INSERT INTO proyectos(
            nombre, cliente, obra, ubicacion, elemento, contratista, supervisor,
            logo_izquierdo, logo_derecho, altura_objetivo_m, nivel_inicial_m,
            nivel_final_m, volumen_estimado_m3, area_cimbra_m2,
            fecha_inicio_programada, fecha_fin_programada, activo
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(nombre) DO UPDATE SET
            cliente = excluded.cliente,
            obra = excluded.obra,
            ubicacion = excluded.ubicacion,
            elemento = excluded.elemento,
            contratista = excluded.contratista,
            supervisor = excluded.supervisor,
            logo_izquierdo = excluded.logo_izquierdo,
            logo_derecho = excluded.logo_derecho,
            altura_objetivo_m = excluded.altura_objetivo_m,
            nivel_inicial_m = excluded.nivel_inicial_m,
            nivel_final_m = excluded.nivel_final_m,
            volumen_estimado_m3 = excluded.volumen_estimado_m3,
            area_cimbra_m2 = excluded.area_cimbra_m2,
            fecha_inicio_programada = excluded.fecha_inicio_programada,
            fecha_fin_programada = excluded.fecha_fin_programada,
            activo = excluded.activo
        RETURNING id
        """,
        (
            name,
            _optional_text(payload.get("cliente")),
            _optional_text(payload.get("obra")),
            _optional_text(payload.get("ubicacion")),
            _optional_text(payload.get("elemento")),
            _optional_text(payload.get("contratista")),
            _optional_text(payload.get("supervisor")),
            _optional_text(payload.get("logo_izquierdo")),
            _optional_text(payload.get("logo_derecho")),
            optional_float(payload.get("altura_objetivo_m")),
            optional_float(payload.get("nivel_inicial_m")),
            optional_float(payload.get("nivel_final_m")),
            optional_float(payload.get("volumen_estimado_m3")),
            optional_float(payload.get("area_cimbra_m2")),
            _optional_text(payload.get("fecha_inicio_programada")),
            _optional_text(payload.get("fecha_fin_programada")),
            _bool_int(payload.get("activo", 1)),
        ),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def _optional_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _bool_int(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if value in (None, ""):
        return 0
    if isinstance(value, str):
        return 1 if value.lower() in ("1", "true", "on", "yes", "si", "sí") else 0
    return 1 if value else 0


__all__ = ["get_active_project", "upsert_project"]
